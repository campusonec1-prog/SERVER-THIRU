from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import Q

from library.models import LibraryTransaction, LibraryFine
from users.models import User
from leave.models import Notification


class Command(BaseCommand):
    help = 'Dispatches morning 9:00 AM overdue notifications for library borrowers.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fine-per-day',
            type=float,
            default=2.0,
            help='Fine per day in Rupees (default: 2.00)'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force sending notifications even if already notified today'
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        fine_rate = Decimal(str(options['fine_per_day']))
        force = options.get('force', False)

        self.stdout.write(self.style.NOTICE(f'Starting daily overdue library notification dispatch for {today}...'))

        overdue_loans = LibraryTransaction.objects.filter(
            returned_on__isnull=True,
            due_on__lt=today
        ).select_related('member', 'member__student', 'member__user', 'book')

        notified_count = 0
        skipped_count = 0
        total_fines = Decimal('0.00')

        for loan in overdue_loans:
            days = (today - loan.due_on).days
            if days <= 0:
                continue

            fine_amt = Decimal(str(days)) * fine_rate
            total_fines += fine_amt

            # Ensure overdue fine record exists
            fine_rec, created = LibraryFine.objects.get_or_create(
                transaction=loan,
                defaults={
                    'member': loan.member,
                    'book': loan.book,
                    'due_on': loan.due_on,
                    'overdue_days': days,
                    'fine_rate_per_day': fine_rate,
                    'fine_amount': fine_amt,
                    'status': 'PENDING',
                }
            )
            if not created and fine_rec.status == 'PENDING':
                fine_rec.overdue_days = days
                fine_rec.fine_amount = fine_amt
                fine_rec.save()

            # Find recipient user
            target_user = None
            if loan.member.user:
                target_user = loan.member.user
            elif loan.member.student:
                stu = loan.member.student
                target_user = User.objects.filter(
                    Q(username=stu.roll_number) | Q(username=stu.register_number)
                ).first()

            if not target_user:
                continue

            # Check if notification was already sent today (unless forced)
            if not force:
                already_sent = Notification.objects.filter(
                    user=target_user,
                    created_at__date=today,
                    title__icontains='Overdue Library Book',
                    message__icontains=loan.book.acc_no or loan.book.title[:20]
                ).exists()
                if already_sent:
                    skipped_count += 1
                    continue

            Notification.objects.create(
                user=target_user,
                title=f'Overdue Library Book: {loan.book.title[:50]}',
                message=(
                    f'Your borrowed book "{loan.book.title}" (Acc: {loan.book.acc_no}) was due on {loan.due_on} '
                    f'and is now {days} day(s) overdue. Current fine: Rs. {fine_amt:.2f}. '
                    f'Please return or renew it at the Central Library counter today.'
                ),
                notification_type='GENERAL',
            )
            notified_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully completed! Notified: {notified_count} borrowers. '
                f'Skipped (already sent today): {skipped_count}. Total overdue fines accrued: Rs. {total_fines:.2f}'
            )
        )
