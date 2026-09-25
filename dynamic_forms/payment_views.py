import logging
import time
import razorpay
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import Application, ApplicationFee, PaymentTransaction, PaymentStatus, ApplicationUser
from .serializers import PaymentTransactionSerializer
from institution.models import AcademicYear

logger = logging.getLogger('payments')


def get_razorpay_client():
    """Initialize and return the Razorpay Client with credentials from settings."""
    key_id = getattr(settings, 'RAZORPAY_KEY_ID', '').strip()
    secret_key = getattr(settings, 'RAZORPAY_SECRET_KEY', '').strip()

    if not key_id or not secret_key:
        logger.error("[Razorpay Init Error] RAZORPAY_KEY_ID or RAZORPAY_SECRET_KEY is missing in backend settings.")
        raise ValueError("Razorpay payment gateway credentials are not configured on the server.")

    client = razorpay.Client(auth=(key_id, secret_key))
    client.set_app_details({"title": "TEC-IMS", "version": "1.0.0"})
    return client


def resolve_application_fee(application=None, program=None, program_id=None):
    """
    Authoritatively resolve the fee configuration from the database.
    Lookup Hierarchy:
      1. Program + Active Academic Year
      2. Program + Global (academic_year is NULL)
      3. Global (program is NULL) + Active Academic Year
      4. Global (program is NULL and academic_year is NULL)
      5. Any active ApplicationFee record
    """
    active_ay = AcademicYear.objects.filter(is_display=True, is_active=True).first()
    if not active_ay:
        active_ay = AcademicYear.objects.filter(is_active=True).first()

    fee_config = None
    target_program = None
    if application and application.program:
        target_program = application.program
    elif program:
        target_program = program
    elif program_id:
        from institution.models import Program
        target_program = Program.objects.filter(pk=program_id).first()

    if target_program:
        if active_ay:
            fee_config = ApplicationFee.objects.filter(
                program=target_program,
                academic_year=active_ay,
                is_active=True
            ).first()

        if not fee_config:
            fee_config = ApplicationFee.objects.filter(
                program=target_program,
                academic_year__isnull=True,
                is_active=True
            ).first()

    if not fee_config:
        if active_ay:
            fee_config = ApplicationFee.objects.filter(
                program__isnull=True,
                academic_year=active_ay,
                is_active=True
            ).first()

        if not fee_config:
            fee_config = ApplicationFee.objects.filter(
                program__isnull=True,
                academic_year__isnull=True,
                is_active=True
            ).first()

    if not fee_config:
        fee_config = ApplicationFee.objects.filter(is_active=True).first()

    if fee_config:
        app_fee = Decimal(str(fee_config.application_fee or 0))
        plat_fee = Decimal(str(fee_config.platform_fee or 0))
        total_amount = app_fee + plat_fee
        return {
            'fee_config_id': fee_config.id,
            'application_fee': app_fee,
            'platform_fee': plat_fee,
            'total_amount': total_amount,
            'currency': 'INR'
        }

    # Default fallback if no fee record has been configured yet
    return {
        'fee_config_id': None,
        'application_fee': Decimal('1000.00'),
        'platform_fee': Decimal('50.00'),
        'total_amount': Decimal('1050.00'),
        'currency': 'INR'
    }


def check_application_access(user, application):
    """Check whether the authenticated user has rights to access/pay for this application."""
    is_admin = False
    try:
        role_name = getattr(user.role, 'role_name', '').upper()
        if role_name in ['ADMIN', 'ADMINISTRATOR', 'SUPERADMIN', 'STAFF']:
            is_admin = True
    except AttributeError:
        pass

    if getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False):
        is_admin = True

    if is_admin:
        return True

    if isinstance(user, ApplicationUser) or user.__class__.__name__ == 'ApplicationUser':
        if application.candidate_id == user.id:
            return True

    # Check candidate email match
    user_email = getattr(user, 'email', getattr(user, 'mail', None))
    if user_email and application.candidate and application.candidate.email == user_email:
        return True

    return False


class PaymentSummaryView(APIView):
    """
    GET /api/forms/payments/summary/<int:application_id>/
    Fetches the authoritative payment summary and fee breakdown for an application.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, application_id):
        try:
            application = Application.objects.select_related('candidate', 'program').get(pk=application_id)
        except Application.DoesNotExist:
            return Response({
                "code": 404,
                "message": "Application not found."
            }, status=status.HTTP_404_NOT_FOUND)

        if not check_application_access(request.user, application):
            raise PermissionDenied("You are not authorized to view the payment summary for this application.")

        fee_info = resolve_application_fee(application)

        # Check latest transaction if any
        latest_tx = PaymentTransaction.objects.filter(application=application).order_by('-id').first()

        return Response({
            "code": 200,
            "message": "Payment summary retrieved successfully",
            "data": {
                "application_id": application.id,
                "application_no": application.application_no,
                "candidate_name": application.candidate.name if application.candidate else '',
                "candidate_email": application.candidate.email if application.candidate else '',
                "candidate_phone": application.candidate.phone_number if application.candidate else '',
                "program_name": application.program.program_name if application.program else 'General Admission',
                "payment_status": application.payment_status,
                "paid_amount": float(application.paid_amount) if application.paid_amount else None,
                "paid_at": application.paid_at.isoformat() if application.paid_at else None,
                "application_fee": float(fee_info['application_fee']),
                "platform_fee": float(fee_info['platform_fee']),
                "total_amount": float(fee_info['total_amount']),
                "currency": fee_info['currency'],
                "razorpay_key_id": getattr(settings, 'RAZORPAY_KEY_ID', '').strip(),
                "latest_transaction": {
                    "id": latest_tx.id,
                    "order_id": latest_tx.razorpay_order_id,
                    "payment_id": latest_tx.razorpay_payment_id,
                    "status": latest_tx.status,
                    "paid_at": latest_tx.paid_at.isoformat() if latest_tx.paid_at else None
                } if latest_tx else None
            }
        }, status=status.HTTP_200_OK)


class CreateRazorpayOrderView(APIView):
    """
    POST /api/forms/payments/create-order/
    Creates an official Razorpay order with authoritative fees calculated strictly on the backend.
    Supports either application_id or program_id (for pre-payment application flows).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        application_id = request.data.get('application_id') or request.data.get('applicationId')
        program_id = request.data.get('program_id') or request.data.get('programId')

        if not application_id and not program_id:
            return Response({
                "code": 400,
                "message": "Either application_id or program_id is required."
            }, status=status.HTTP_400_BAD_REQUEST)

        application = None
        target_program = None

        if application_id:
            try:
                application = Application.objects.select_related('candidate', 'program').get(pk=application_id)
            except Application.DoesNotExist:
                return Response({
                    "code": 404,
                    "message": "Application not found."
                }, status=status.HTTP_404_NOT_FOUND)

            if not check_application_access(request.user, application):
                raise PermissionDenied("You are not authorized to initiate payment for this application.")

            # Guard: Check if application is already paid
            if application.payment_status == 'PAID':
                logger.info(f"[Payment Notice] Application {application.application_no} (ID: {application.id}) is already paid.")
                return Response({
                    "code": 200,
                    "message": "Application fee has already been paid successfully.",
                    "data": {
                        "already_paid": True,
                        "application_id": application.id,
                        "application_no": application.application_no,
                        "payment_status": application.payment_status,
                        "paid_amount": float(application.paid_amount or 0),
                        "paid_at": application.paid_at.isoformat() if application.paid_at else None
                    }
                }, status=status.HTTP_200_OK)

            target_program = application.program
        elif program_id:
            from institution.models import Program
            target_program = Program.objects.filter(pk=program_id).first()
            if not target_program:
                return Response({
                    "code": 404,
                    "message": "Selected program not found."
                }, status=status.HTTP_404_NOT_FOUND)

        # Calculate authoritative amount strictly from backend
        fee_info = resolve_application_fee(application=application, program=target_program)
        total_amount = fee_info['total_amount']
        app_fee = fee_info['application_fee']
        plat_fee = fee_info['platform_fee']

        if total_amount <= 0:
            return Response({
                "code": 400,
                "message": "Invalid payment configuration: payable amount must be greater than zero."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Razorpay expects amount in paise (1 INR = 100 paise)
        amount_in_paise = int(total_amount * 100)

        # Get candidate user
        candidate = application.candidate if application else (request.user if isinstance(request.user, ApplicationUser) else None)
        if not candidate and request.user.is_authenticated:
            candidate = request.user

        try:
            client = get_razorpay_client()
        except ValueError as e:
            return Response({
                "code": 500,
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        receipt_str = f"rcpt_{application.id if application else target_program.id}_{request.user.id}_{int(time.time())}"[:40]

        order_payload = {
            'amount': amount_in_paise,
            'currency': 'INR',
            'receipt': receipt_str,
            'notes': {
                'application_id': str(application.id) if application else '',
                'application_no': str(application.application_no or '') if application else '',
                'program_id': str(target_program.id if target_program else ''),
                'candidate_id': str(candidate.id) if candidate else str(request.user.id),
                'candidate_email': str(candidate.email if candidate else request.user.email or ''),
                'program_name': str(target_program.program_name if target_program else '')
            }
        }

        logger.info(f"[Payment Order Creation Started] Target: {target_program or application}, Total Amount: ₹{total_amount} ({amount_in_paise} paise)")

        try:
            razorpay_order = client.order.create(data=order_payload)
        except Exception as e:
            logger.error(f"[Razorpay Order Creation Failed] Error: {str(e)}", exc_info=True)
            return Response({
                "code": 502,
                "message": "Unable to initiate payment with Razorpay. Please try again in a few moments."
            }, status=status.HTTP_502_BAD_GATEWAY)

        order_id = razorpay_order.get('id')
        if not order_id:
            logger.error(f"[Razorpay Order Invalid] Missing order id in response: {razorpay_order}")
            return Response({
                "code": 502,
                "message": "Invalid response received from Razorpay gateway."
            }, status=status.HTTP_502_BAD_GATEWAY)

        # Store transaction record in database
        try:
            with transaction.atomic():
                if application:
                    # Mark any previous pending transaction as CANCELLED to avoid confusion
                    PaymentTransaction.objects.filter(
                        application=application,
                        status__in=[PaymentStatus.CREATED, PaymentStatus.PENDING]
                    ).update(status=PaymentStatus.CANCELLED)

                payment_tx = PaymentTransaction.objects.create(
                    application=application,
                    user=candidate,
                    razorpay_order_id=order_id,
                    amount=total_amount,
                    application_fee=app_fee,
                    platform_fee=plat_fee,
                    currency='INR',
                    status=PaymentStatus.CREATED,
                    razorpay_order_response=razorpay_order
                )
        except Exception as e:
            logger.error(f"[PaymentTransaction DB Save Error] Order ID: {order_id}, Error: {str(e)}", exc_info=True)
            return Response({
                "code": 500,
                "message": "Failed to record payment transaction on server."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.info(f"[Payment Order Created Successfully] Transaction ID: {payment_tx.id}, Razorpay Order ID: {order_id}")

        return Response({
            "code": 200,
            "message": "Payment order created successfully",
            "data": {
                "razorpay_key_id": getattr(settings, 'RAZORPAY_KEY_ID', '').strip(),
                "order_id": order_id,
                "transaction_id": payment_tx.id,
                "amount": amount_in_paise,
                "currency": "INR",
                "application_fee": float(app_fee),
                "platform_fee": float(plat_fee),
                "total_amount": float(total_amount),
                "application_id": application.id if application else None,
                "application_no": application.application_no if application else None,
                "candidate_name": getattr(candidate, 'name', '') or getattr(candidate, 'username', '') or '',
                "candidate_email": getattr(candidate, 'email', '') or '',
                "candidate_phone": getattr(candidate, 'phone_number', '') or ''
            }
        }, status=status.HTTP_200_OK)


class VerifyRazorpayPaymentView(APIView):
    """
    POST /api/forms/payments/verify/
    Verifies Razorpay payment signature cryptographically, fetches order/payment from Razorpay,
    and updates database records safely.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        razorpay_order_id = request.data.get('razorpay_order_id')
        razorpay_payment_id = request.data.get('razorpay_payment_id')
        razorpay_signature = request.data.get('razorpay_signature')

        if not razorpay_order_id or not razorpay_payment_id or not razorpay_signature:
            return Response({
                "code": 400,
                "message": "Missing payment verification parameters (order_id, payment_id, and signature are required)."
            }, status=status.HTTP_400_BAD_REQUEST)

        logger.info(f"[Payment Verification Started] Order ID: {razorpay_order_id}, Payment ID: {razorpay_payment_id}")

        # Locate matching payment transaction
        try:
            payment_tx = PaymentTransaction.objects.select_related('application', 'user', 'application__candidate').get(
                razorpay_order_id=razorpay_order_id
            )
        except PaymentTransaction.DoesNotExist:
            logger.warning(f"[Payment Verification Warning] No transaction found for order ID {razorpay_order_id}")
            return Response({
                "code": 404,
                "message": "Invalid payment order reference. Transaction not found."
            }, status=status.HTTP_404_NOT_FOUND)

        application = payment_tx.application

        # Authorize access
        if application and not check_application_access(request.user, application):
            raise PermissionDenied("You are not authorized to verify payment for this application.")

        # Idempotency check: If already SUCCESS, return success response immediately
        if payment_tx.status == PaymentStatus.SUCCESS:
            logger.info(f"[Payment Verification Idempotent] Transaction {payment_tx.id} already verified as SUCCESS.")
            return Response({
                "code": 200,
                "message": "Payment has already been verified and recorded successfully.",
                "data": {
                    "payment_id": payment_tx.razorpay_payment_id or razorpay_payment_id,
                    "order_id": payment_tx.razorpay_order_id,
                    "status": "SUCCESS",
                    "amount": float(payment_tx.amount),
                    "currency": payment_tx.currency,
                    "paid_at": payment_tx.paid_at.isoformat() if payment_tx.paid_at else None,
                    "application_id": application.id if application else None,
                    "application_no": application.application_no if application else None
                }
            }, status=status.HTTP_200_OK)

        if application and application.payment_status == 'PAID' and payment_tx.status != PaymentStatus.SUCCESS:
            logger.info(f"[Payment Verification Notice] Application {application.application_no} already marked PAID.")
            payment_tx.status = PaymentStatus.SUCCESS
            payment_tx.razorpay_payment_id = razorpay_payment_id
            payment_tx.razorpay_signature = razorpay_signature
            payment_tx.save()
            return Response({
                "code": 200,
                "message": "Payment verified successfully.",
                "data": {
                    "payment_id": razorpay_payment_id,
                    "order_id": razorpay_order_id,
                    "status": "SUCCESS",
                    "amount": float(payment_tx.amount),
                    "currency": payment_tx.currency,
                    "paid_at": application.paid_at.isoformat() if application.paid_at else timezone.now().isoformat(),
                    "application_id": application.id,
                    "application_no": application.application_no
                }
            }, status=status.HTTP_200_OK)

        # 1. Cryptographic Signature Verification
        try:
            client = get_razorpay_client()
        except ValueError as e:
            return Response({
                "code": 500,
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        params_dict = {
            'razorpay_order_id': str(razorpay_order_id).strip(),
            'razorpay_payment_id': str(razorpay_payment_id).strip(),
            'razorpay_signature': str(razorpay_signature).strip()
        }

        try:
            client.utility.verify_payment_signature(params_dict)
            logger.info(f"[Signature Verification Passed] Order ID: {razorpay_order_id}, Payment ID: {razorpay_payment_id}")
        except razorpay.errors.SignatureVerificationError as sve:
            logger.error(f"[Signature Verification FAILED] Order ID: {razorpay_order_id}, Payment ID: {razorpay_payment_id}, Error: {str(sve)}")
            payment_tx.status = PaymentStatus.FAILED
            payment_tx.error_code = "SIGNATURE_VERIFICATION_FAILED"
            payment_tx.error_description = "Cryptographic signature verification failed."
            payment_tx.save(update_fields=['status', 'error_code', 'error_description'])
            return Response({
                "code": 400,
                "message": "Payment signature verification failed. The transaction cannot be validated."
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"[Signature Verification Error] Order ID: {razorpay_order_id}, Error: {str(e)}", exc_info=True)
            return Response({
                "code": 400,
                "message": "Failed to verify payment signature."
            }, status=status.HTTP_400_BAD_REQUEST)

        # 2. Server-to-Server Payment Fetch from Razorpay
        try:
            payment_details = client.payment.fetch(str(razorpay_payment_id).strip())
        except Exception as e:
            logger.error(f"[Razorpay Payment Fetch Error] Payment ID: {razorpay_payment_id}, Error: {str(e)}", exc_info=True)
            return Response({
                "code": 502,
                "message": "Signature verified, but failed to fetch payment status from Razorpay."
            }, status=status.HTTP_502_BAD_GATEWAY)

        # 3. Validate Fetched Payment Properties
        fetched_order_id = payment_details.get('order_id')
        fetched_amount = payment_details.get('amount')
        fetched_currency = payment_details.get('currency', 'INR')
        fetched_status = payment_details.get('status')
        payment_method = payment_details.get('method', 'online')

        expected_amount_paise = int(payment_tx.amount * 100)

        if fetched_order_id != razorpay_order_id:
            logger.error(f"[Payment Order Mismatch] Expected: {razorpay_order_id}, Got: {fetched_order_id}")
            payment_tx.status = PaymentStatus.FAILED
            payment_tx.error_code = "ORDER_MISMATCH"
            payment_tx.error_description = f"Payment order mismatch: expected {razorpay_order_id}, got {fetched_order_id}"
            payment_tx.save(update_fields=['status', 'error_code', 'error_description'])
            return Response({
                "code": 400,
                "message": "Payment does not match the initiated order."
            }, status=status.HTTP_400_BAD_REQUEST)

        if fetched_amount != expected_amount_paise:
            logger.error(f"[Payment Amount Mismatch] Expected: {expected_amount_paise} paise, Got: {fetched_amount} paise")
            payment_tx.status = PaymentStatus.FAILED
            payment_tx.error_code = "AMOUNT_MISMATCH"
            payment_tx.error_description = f"Amount mismatch: expected {expected_amount_paise}, got {fetched_amount}"
            payment_tx.save(update_fields=['status', 'error_code', 'error_description'])
            return Response({
                "code": 400,
                "message": "Payment amount mismatch detected."
            }, status=status.HTTP_400_BAD_REQUEST)

        if fetched_status not in ['captured', 'authorized']:
            logger.error(f"[Payment Status Invalid] Status: {fetched_status}")
            payment_tx.status = PaymentStatus.FAILED
            payment_tx.error_code = "STATUS_NOT_CAPTURED"
            payment_tx.error_description = f"Payment is in {fetched_status} state."
            payment_tx.save(update_fields=['status', 'error_code', 'error_description'])
            return Response({
                "code": 400,
                "message": f"Payment is not in a captured state (current state: {fetched_status})."
            }, status=status.HTTP_400_BAD_REQUEST)

        # If authorized, auto-capture it
        if fetched_status == 'authorized':
            try:
                payment_details = client.payment.capture(razorpay_payment_id, expected_amount_paise)
                logger.info(f"[Payment Auto-Captured] Payment ID: {razorpay_payment_id}")
            except Exception as e:
                logger.warning(f"[Payment Capture Notice] Could not explicitly capture payment {razorpay_payment_id}: {e}")

        # 4. Atomically persist successful payment and mark application PAID
        now = timezone.now()
        try:
            with transaction.atomic():
                payment_tx.razorpay_payment_id = razorpay_payment_id
                payment_tx.razorpay_signature = razorpay_signature
                payment_tx.status = PaymentStatus.SUCCESS
                payment_tx.payment_method = payment_method
                payment_tx.razorpay_payment_response = payment_details
                payment_tx.razorpay_signature_verification_response = {
                    'verified': True,
                    'verified_at': now.isoformat(),
                    'method': 'SDK_HMAC_SHA256'
                }
                payment_tx.paid_at = now
                payment_tx.error_code = None
                payment_tx.error_description = None
                payment_tx.save()

                if application:
                    application.payment_status = 'PAID'
                    application.paid_amount = payment_tx.amount
                    application.paid_at = now
                    application.save(update_fields=['payment_status', 'paid_amount', 'paid_at'])

        except Exception as e:
            logger.error(f"[Payment DB Update Error] Failed to update application payment status: {e}", exc_info=True)
            return Response({
                "code": 500,
                "message": "Payment verified but server failed to update application status."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        logger.info(f"[Payment Verification SUCCESS] App ID: {application.id if application else None}, Order: {razorpay_order_id}, Payment: {razorpay_payment_id}, Amount: ₹{payment_tx.amount}")

        return Response({
            "code": 200,
            "message": "Payment verified and recorded successfully.",
            "data": {
                "payment_id": razorpay_payment_id,
                "order_id": razorpay_order_id,
                "status": "SUCCESS",
                "amount": float(payment_tx.amount),
                "currency": payment_tx.currency,
                "paid_at": now.isoformat(),
                "application_id": application.id if application else None,
                "application_no": application.application_no if application else None,
                "candidate_name": application.candidate.name if (application and application.candidate) else (getattr(payment_tx.user, 'name', '') or '')
            }
        }, status=status.HTTP_200_OK)


class RazorpayWebhookView(APIView):
    """
    POST /api/forms/payments/webhook/
    Webhook endpoint for Razorpay server-to-server event reconciliation.
    """
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        webhook_signature = request.headers.get('X-Razorpay-Signature')
        webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', '').strip()

        if webhook_secret and webhook_signature:
            try:
                client = get_razorpay_client()
                client.utility.verify_webhook_signature(
                    request.body.decode('utf-8'),
                    webhook_signature,
                    webhook_secret
                )
            except Exception as e:
                logger.warning(f"[Webhook Signature Mismatch] {e}")
                return Response({"status": "invalid_signature"}, status=status.HTTP_400_BAD_REQUEST)

        event_data = request.data
        event_name = event_data.get('event')
        payload = event_data.get('payload', {})

        logger.info(f"[Razorpay Webhook Received] Event: {event_name}")

        if event_name in ['payment.captured', 'order.paid']:
            payment_obj = payload.get('payment', {}).get('entity', {})
            order_id = payment_obj.get('order_id')
            payment_id = payment_obj.get('id')

            if order_id:
                try:
                    tx = PaymentTransaction.objects.select_related('application').get(razorpay_order_id=order_id)
                    if tx.status != PaymentStatus.SUCCESS:
                        now = timezone.now()
                        with transaction.atomic():
                            tx.status = PaymentStatus.SUCCESS
                            tx.razorpay_payment_id = payment_id or tx.razorpay_payment_id
                            tx.razorpay_payment_response = payment_obj
                            tx.payment_method = payment_obj.get('method', tx.payment_method)
                            tx.paid_at = now
                            tx.save()

                            app = tx.application
                            app.payment_status = 'PAID'
                            app.paid_amount = tx.amount
                            app.paid_at = now
                            app.save(update_fields=['payment_status', 'paid_amount', 'paid_at'])

                        logger.info(f"[Webhook Reconciliation SUCCESS] Reconciled Order: {order_id} -> App {app.application_no} marked PAID.")
                except PaymentTransaction.DoesNotExist:
                    logger.warning(f"[Webhook Notice] Order {order_id} not found in database.")

        elif event_name == 'payment.failed':
            payment_obj = payload.get('payment', {}).get('entity', {})
            order_id = payment_obj.get('order_id')
            if order_id:
                PaymentTransaction.objects.filter(
                    razorpay_order_id=order_id,
                    status__in=[PaymentStatus.CREATED, PaymentStatus.PENDING]
                ).update(
                    status=PaymentStatus.FAILED,
                    error_code=payment_obj.get('error_code', 'PAYMENT_FAILED'),
                    error_description=payment_obj.get('error_description', 'Payment failed on Razorpay')
                )

        return Response({"status": "ok"}, status=status.HTTP_200_OK)
