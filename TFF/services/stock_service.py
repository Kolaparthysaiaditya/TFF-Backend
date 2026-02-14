from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from ..models import BranchStock, GodownStock, StockRequest, Branch, Item

# ✅ Find branch with excess stock
def find_excess_branch(requesting_branch, item, quantity):
    stocks = BranchStock.objects.select_related("branch").filter(
        item=item,
        quantity__gt=quantity,
    ).exclude(branch=requesting_branch)

    for stock in stocks:
        excess = stock.quantity - stock.min_level
        if excess >= quantity:
            return stock.branch
    return None

# ✅ Create smart stock request
def create_smart_stock_request(branch, item, quantity):
    excess_branch = find_excess_branch(branch, item, quantity)
    expiry = timezone.now() + timedelta(minutes=15)

    if excess_branch:
        return StockRequest.objects.create(
            from_branch=branch,
            to_branch=excess_branch,
            item=item,
            quantity=quantity,
            expires_at=expiry,
            from_godown=False
        )
    else:
        return StockRequest.objects.create(
            from_branch=branch,
            item=item,
            quantity=quantity,
            from_godown=True
        )

# ✅ Approve inter-branch request
@transaction.atomic
def approve_inter_branch_request(req):
    from_branch = req.to_branch
    to_branch = req.from_branch
    item = req.item
    qty = req.quantity

    from_stock = BranchStock.objects.select_for_update().get(branch=from_branch, item=item)
    if from_stock.quantity < qty:
        raise Exception("Insufficient stock")

    to_stock, _ = BranchStock.objects.get_or_create(branch=to_branch, item=item, defaults={"quantity": 0, "min_level": 0})
    from_stock.quantity -= qty
    to_stock.quantity += qty
    from_stock.save()
    to_stock.save()

    req.status = "approved"
    req.save()

# ✅ Approve godown request
@transaction.atomic
def approve_godown_request(req):
    godown_stock = GodownStock.objects.select_for_update().get(item=req.item)
    if godown_stock.quantity < req.quantity:
        raise Exception("Insufficient godown stock")

    branch_stock, _ = BranchStock.objects.get_or_create(branch=req.from_branch, item=req.item, defaults={"quantity": 0, "min_level": 0})
    godown_stock.quantity -= req.quantity
    branch_stock.quantity += req.quantity
    godown_stock.save()
    branch_stock.save()

    req.status = "approved"
    req.save()

# ✅ Handle expired inter-branch requests
def handle_stock_request_timeouts():
    now = timezone.now()
    expired_requests = StockRequest.objects.filter(status="pending", from_godown=False, expires_at__lt=now)

    for req in expired_requests:
        req.status = "timeout"
        req.save()
        # fallback to godown
        StockRequest.objects.create(
            from_branch=req.from_branch,
            item=req.item,
            quantity=req.quantity,
            from_godown=True
        )
