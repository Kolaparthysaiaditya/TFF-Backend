from django.contrib import admin
from .models import *

admin.site.register(Branch)
@admin.register(Employees)
class EmployeesAdmin(admin.ModelAdmin):
    list_display = ('username', 'role', 'Eid', 'branch', 'is_active')
admin.site.register(Godown)
admin.site.register(Item)
admin.site.register(BranchStock)
admin.site.register(GodownStock)
admin.site.register(StockRequest)
admin.site.register(Order)
admin.site.register(OrderItem)
admin.site.register(Billing)
admin.site.register(KitchenOrderTicket)
admin.site.register(Expense)
admin.site.register(DailyAnalytics)
admin.site.register(MenuItem)
admin.site.register(BranchMenuItem)
admin.site.register(Offer)
admin.site.register(Cart)
admin.site.register(CartItem)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('Cid', 'name', 'phone', 'created_at')

admin.site.register(Customer, CustomerAdmin)
admin.site.register(TiexCollect)

