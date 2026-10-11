import json
import logging
from decimal import Decimal
from datetime import datetime, date

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from student.models import StudentFees, FeePayment, StudentSemesterFee

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = "Safely and idempotently reconciles historical JSON fee payment records into the FeePayment ledger."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run analysis and report without modifying the database.',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        self.stdout.write(self.style.NOTICE(f"Starting Fee Payment Reconciliation {'(DRY RUN)' if dry_run else ''}..."))

        total_inspected = 0
        total_migrated = 0
        total_skipped = 0
        total_flagged = 0
        discrepancies = []

        all_fees = StudentFees.objects.select_related('student').all().order_by('id')

        for sf in all_fees:
            total_inspected += 1
            remarks_str = (sf.remarks or '').strip()
            student_id = sf.student_id
            roll = sf.student.roll_number or str(student_id)

            history = []
            is_json = False

            if remarks_str:
                try:
                    parsed = json.loads(remarks_str)
                    if isinstance(parsed, dict) and 'history' in parsed and isinstance(parsed['history'], list):
                        history = parsed['history']
                        is_json = True
                except (json.JSONDecodeError, TypeError):
                    is_json = False

            reconstructed_tuition = Decimal('0.00')
            reconstructed_books = Decimal('0.00')

            if is_json and history:
                for idx, tx in enumerate(history):
                    raw_amount = tx.get('amount')
                    if raw_amount is None:
                        continue
                    try:
                        amt = Decimal(str(raw_amount))
                    except Exception:
                        continue

                    if amt <= 0:
                        continue

                    category_raw = str(tx.get('category', 'Academic Fees')).lower()
                    if 'book' in category_raw or 'uniform' in category_raw:
                        fee_category = 'BOOKS'
                        reconstructed_books += amt
                    else:
                        fee_category = 'TUITION'
                        reconstructed_tuition += amt

                    date_str = str(tx.get('date', '')).strip()
                    time_str = str(tx.get('time', '')).strip()
                    pay_date = None

                    if date_str:
                        for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d/%m/%y'):
                            try:
                                pay_date = datetime.strptime(date_str, fmt).date()
                                break
                            except ValueError:
                                pass

                    if not pay_date:
                        pay_date = sf.created_at.date() if sf.created_at else timezone.now().date()

                    pay_mode = tx.get('mode', sf.payment_mode or 'Cash')
                    notes = tx.get('notes', '')
                    proc_user_id = tx.get('processed_by_id')

                    user_obj = None
                    if proc_user_id:
                        user_obj = User.objects.filter(pk=proc_user_id).first()

                    # Idempotency key derived from student, idx, date, and amount
                    idemp_key = f"HIST-SF{sf.id}-TX{idx}-{pay_date}-{amt}"

                    existing_payment = FeePayment.objects.filter(idempotency_key=idemp_key).first()
                    if existing_payment:
                        total_skipped += 1
                        continue

                    receipt_num = f"HIST-{sf.id:04d}-{idx+1:02d}"
                    # Ensure receipt number uniqueness
                    if FeePayment.objects.filter(receipt_number=receipt_num).exists():
                        receipt_num = f"HIST-{sf.id:04d}-{idx+1:02d}-{int(timezone.now().timestamp())}"

                    if not dry_run:
                        with transaction.atomic():
                            FeePayment.objects.create(
                                student_fees=sf,
                                student_semester_fee=None,
                                amount_paid=amt,
                                fee_category=fee_category,
                                payment_mode=pay_mode,
                                payment_date=pay_date,
                                payment_timestamp=timezone.now(),
                                receipt_number=receipt_num,
                                transaction_reference=tx.get('reference', ''),
                                idempotency_key=idemp_key,
                                remarks=notes or f"Migrated from historical JSON record (index {idx})",
                                recorded_by=user_obj,
                                is_reconciled=True
                            )
                    total_migrated += 1

            # Check for discrepancies with ledger
            expected_tuition = sf.paid_amount or Decimal('0.00')
            expected_books = sf.books_fees_paid or Decimal('0.00')

            has_discrepancy = False
            disc_notes = []

            if is_json:
                if reconstructed_tuition != expected_tuition:
                    has_discrepancy = True
                    disc_notes.append(f"Tuition Paid Ledger={expected_tuition} vs History={reconstructed_tuition}")
                if reconstructed_books != expected_books:
                    has_discrepancy = True
                    disc_notes.append(f"Books Paid Ledger={expected_books} vs History={reconstructed_books}")
            elif (expected_tuition > 0 or expected_books > 0) and not is_json:
                has_discrepancy = True
                disc_notes.append(f"Has non-zero paid balance (Tuition={expected_tuition}, Books={expected_books}) but remarks contains no structured JSON history.")

            if has_discrepancy:
                total_flagged += 1
                discrepancies.append({
                    'student_id': student_id,
                    'roll_number': roll,
                    'issues': disc_notes
                })

        # Summary Report
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("RECONCILIATION SUMMARY REPORT"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"Total StudentFees Records Inspected : {total_inspected}")
        self.stdout.write(f"Historical Payments Migrated       : {total_migrated}")
        self.stdout.write(f"Duplicate/Existing Payments Skipped : {total_skipped}")
        self.stdout.write(f"Records Flagged for Review         : {total_flagged}")

        if discrepancies:
            self.stdout.write(self.style.WARNING("\nFlagged Records for Manual Review:"))
            for d in discrepancies[:20]:
                self.stdout.write(f"  Student ID {d['student_id']} ({d['roll_number']}): {'; '.join(d['issues'])}")
            if len(discrepancies) > 20:
                self.stdout.write(f"  ... and {len(discrepancies) - 20} more records.")
        else:
            self.stdout.write(self.style.SUCCESS("\nAll inspected records reconciled with zero discrepancy!"))

        self.stdout.write(self.style.SUCCESS("=" * 60 + "\n"))
