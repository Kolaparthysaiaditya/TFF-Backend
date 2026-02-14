from django.urls import path
from .views import *

urlpatterns = [
    path("nearest-branch/", nearest_branch),
    path("nearest-branch-15/", branches_within_radius),
    path('login/', employee_login),
    path('employee/logout/', employee_logout),
    path("customer/login/", customer_login),
    path("customer/logout/", customer_logout ),
    path("customer/register/", customer_register),
    path('dashboard-counts/', model_counts, name='model-counts'),
    path("branches/create/", create_branch),
    path("branches/<int:id>/update/", update_branch),
    path("branches/<int:id>/delete/", delete_branch),
    path("staff/excess/", excess_staff_list),
    path("staff/assign/", assign_excess_staff),

    path("menu/categories/", menu_categories, name="menu-categories"),
    path("admin/menu/", admin_menu_list),
    path("admin/menu/create/", admin_menu_create),

    path("branch/menu/", branch_menu_list),
    path("branch/<int:branch_id>/menu-all/", branch_menu_with_status),
    path("branch/<int:branch_id>/menu/<int:menu_item_id>/toggle/",toggle_menu_availability),

    path("admin/offers/", admin_all_offers),
    path("today/offer/", customer_today_offers),
    path("manager/offers/", manager_offers),

    path("menu/offer-items/", menu_items_for_offer),
    path("offers/create/", admin_create_offer),
    path("admin/offers/<int:pk>/update/", admin_update_offer),
    path("admin/offers/<int:pk>/delete/", admin_delete_offer),

    path("branches/", branch_list, name="branches"),
    path("branches/active/", active_branch_list, name="active-branches"),
    path("Employee-list/", Employee_list, name="employee"),
    path("branch/employees/", branch_employees_list),
    path("branch/employees/add/", branch_add_employee),
    path("branch/employees/<int:staff_id>/edit/", branch_edit_employee),
    path("branch/employees/<int:staff_id>/delete/", branch_delete_employee),
    path("branch/employees/<int:staff_id>/toggle-working/", branch_toggle_working),


    path("branch/stock/", branch_stock_list),
    path("godown/stock/", godown_stock_list),
    path("godown/create-item/", create_item_and_godown_stock),
    path("branch/dashboard/", branch_dashboard),
    path("stock/request/", smart_stock_request_view),
    path("branches/stock-summary/", branches_stock_summary),
    path("branch/requests/<str:branch_id>/", incoming_branch_requests),
    path("branch/request/respond/<int:request_id>/", respond_branch_request),
    path("godown/request/approve/<int:request_id>/", approve_godown_request_view),
    path("stock/requests/handle-expired/", handle_expired_requests),

    path("cart/add/", add_to_cart),
    path("cart/", view_cart),
    path("cart/update-quantity/", update_cart_quantity),
    path("cart/clear/", clear_cart),
    path("cart/remove-item/", remove_cart_item),

    # Orders – Customer
    path("order/place/", place_order),
    path("orders/current/", current_orders),
    path("orders/history/", order_history),
    path("orders/cancel/", cancel_order),
    
    # Kitchen
    path("kitchen/orders/", kitchen_orders),
    path("chef/orders/accept/", accept_order),
    path("kitchen/orders/complete/", complete_order),
    
    # Chef
    path("kitchen/chef-status/", chef_status),
    path("chef/current-order/", chef_current_order, name="chef-current-order" ),
    path("chef/pending-orders/", pending_orders, name="chef-pending-orders"),
    path("chef/branch-ingredients/", chef_branch_ingredients, name="chef-branch-ingredients"),
    path("chef/submit-ingredients/", submit_ingredient_usage, name="chef-submit-ingredients"),
    path("chef/completed-orders/", chef_completed_orders),

    path("global/summary/", global_summary),
    path("branch/summary/", branch_summary),
    path("branches/leading/", leading_branch, name="leading-branch"),
    path('send-gst-email/', send_gst_email_api, name='send_gst_email_api'),
    path('send-what', send_whatsapp),
]

