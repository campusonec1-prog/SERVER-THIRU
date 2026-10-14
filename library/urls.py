from django.urls import path

from .views import (
    LibraryBookViewSet,
    LibraryDashboardViewSet,
    LibraryMemberViewSet,
    LibraryStudentLookupViewSet,
    LibraryTransactionViewSet,
)

urlpatterns = [
    path('books/list', LibraryBookViewSet.as_view({'get': 'list'}), name='library-books-list'),
    path('books/barcode-lookup', LibraryBookViewSet.as_view({'get': 'barcode_lookup'}), name='library-books-barcode-lookup'),
    path('books/quick-search', LibraryBookViewSet.as_view({'get': 'quick_search'}), name='library-books-quick-search'),
    path('books/create', LibraryBookViewSet.as_view({'post': 'create'}), name='library-books-create'),
    path('books/bulk-import', LibraryBookViewSet.as_view({'post': 'bulk_import'}), name='library-books-bulk-import'),
    path('books/get/<int:pk>', LibraryBookViewSet.as_view({'get': 'retrieve'}), name='library-books-detail'),
    path('books/edit/<int:pk>', LibraryBookViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='library-books-edit'),
    path('books/remove/<int:pk>', LibraryBookViewSet.as_view({'delete': 'destroy'}), name='library-books-remove'),
    path('members/list', LibraryMemberViewSet.as_view({'get': 'list'}), name='library-members-list'),
    path('members/barcode-lookup', LibraryMemberViewSet.as_view({'get': 'barcode_lookup'}), name='library-members-barcode-lookup'),
    path('members/quick-search', LibraryMemberViewSet.as_view({'get': 'quick_search'}), name='library-members-quick-search'),
    path('members/create', LibraryMemberViewSet.as_view({'post': 'create'}), name='library-members-create'),
    path('members/get/<int:pk>', LibraryMemberViewSet.as_view({'get': 'retrieve'}), name='library-members-detail'),
    path('members/edit/<int:pk>', LibraryMemberViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='library-members-edit'),
    path('members/remove/<int:pk>', LibraryMemberViewSet.as_view({'delete': 'destroy'}), name='library-members-remove'),
    path('transactions/list', LibraryTransactionViewSet.as_view({'get': 'list'}), name='library-transactions-list'),
    path('transactions/lookup-by-barcode', LibraryTransactionViewSet.as_view({'get': 'lookup_by_barcode'}), name='library-transactions-lookup-barcode'),
    path('transactions/scan-action', LibraryTransactionViewSet.as_view({'post': 'scan_action'}), name='library-transactions-scan-action'),
    path('transactions/create', LibraryTransactionViewSet.as_view({'post': 'create'}), name='library-transactions-create'),
    path('transactions/get/<int:pk>', LibraryTransactionViewSet.as_view({'get': 'retrieve'}), name='library-transactions-detail'),
    path('transactions/edit/<int:pk>', LibraryTransactionViewSet.as_view({'put': 'update', 'patch': 'partial_update'}), name='library-transactions-edit'),
    path('transactions/return/<int:pk>', LibraryTransactionViewSet.as_view({'post': 'return_book'}), name='library-transactions-return'),
    path('transactions/renew/<int:pk>', LibraryTransactionViewSet.as_view({'post': 'renew'}), name='library-transactions-renew'),
    path('dashboard/summary', LibraryDashboardViewSet.as_view({'get': 'summary'}), name='library-dashboard-summary'),
    path('students/list', LibraryStudentLookupViewSet.as_view({'get': 'list'}), name='library-student-lookup'),
]
