from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from django.utils import timezone
from django.utils.timezone import make_aware, datetime, now
from calendar import monthrange, month_name
from datetime import date
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.hashers import check_password
from django.db import IntegrityError
from django.db.models import Sum, Count
from .utils import haversine
from decimal import Decimal
from .serializers import *
from .models import *
from .services.stock_service import *
from geopy.geocoders import Nominatim
import re
from math import radians, cos, sin, asin, sqrt
from TFF.tasks import send_monthly_gst_email, send_monthly_gst_whatsapp

def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # Earth radius in km
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return R * c 

@api_view(['GET'])
def branches_within_radius(request):
    try:
        lat = float(request.GET.get('lat'))
        lon = float(request.GET.get('lon'))
    except (TypeError, ValueError):
        return Response({"error": "Invalid coordinates"}, status=400)

    max_distance_km = 50  # 15 km radius
    branches_in_range = []

    for branch in Branch.objects.filter(status='active'):
        try:
            branch_lat = float(branch.latitude)
            branch_lon = float(branch.longitude)
        except (TypeError, ValueError):
            continue  # skip branches with invalid coordinates

        distance = haversine(lat, lon, branch_lat, branch_lon)
        if distance <= max_distance_km:
            branches_in_range.append({
                "branch_id": branch.id,
                "branch_code": branch.branch_code,
                "branch_name": branch.branch_name,
                "distance_km": round(distance, 2)
            })

    return Response({"branches": branches_in_range})

def apply_offer(item_id):
    today = timezone.now().date()

    try:
        offer = Offer.objects.get(
            menu_item__id=item_id,
            start_date__lte=today,
            end_date__gte=today,
            is_active=True
        )
    except Offer.DoesNotExist:
        return Decimal("0.00")

    menuitem = MenuItem.objects.get(id=item_id)

    if offer.offer_type == "upto":
        # percentage discount
        discount_price = (menuitem.price * offer.discount_value) / Decimal("100")
        return discount_price.quantize(Decimal("0.01"))

    if offer.offer_type == "flat":
        return Decimal(offer.discount_value)

    return Decimal("0.00")

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

@api_view(['GET'])
def nearest_branch(request):
    try:
        lat = float(request.GET.get('lat'))
        lon = float(request.GET.get('lon'))
        print("hello")
    except (TypeError, ValueError):
        return Response({"error": "Invalid coordinates"}, status=400)

    nearest = None
    min_distance = 3100  # meters

    for branch in Branch.objects.filter(status='active'):
        print(branch.latitude, branch.longitude)
        distance = haversine(
            lat, lon,
            float(branch.latitude),
            float(branch.longitude)
        )
        if distance <= min_distance:
            nearest = branch
            min_distance = distance

    if not nearest:
        return Response({"branch": None})

    return Response({
        "branch_id": nearest.id,
        "branch_code": nearest.branch_code,
        "branch_name": nearest.branch_name,
        "distance": round(min_distance, 2)
    })

@api_view(["GET"])
def menu_items_for_offer(request):
    items = MenuItem.objects.filter(is_active=True)

    data = [
        {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "price": item.price,
            "is_veg": item.is_veg,
        }
        for item in items
    ]
    return Response(data)

@api_view(['POST'])
def employee_login(request):
    phone = request.data.get("phone")
    password = request.data.get("password")

    try:
        employee = Employees.objects.get(phone=phone, is_active=True)
    except Employees.DoesNotExist:
        return Response({"error": "Invalid Phone No"}, status=401)

    if not employee.check_password(password):
        return Response({"error": "Invalid password"}, status=401)

    refresh = RefreshToken.for_user(employee)

    employee.is_logged_in = True
    employee.save(update_fields=["is_logged_in"])

    return Response({
        "status": "success",
        "tokens": {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        },
        "user": {
            "eid": employee.Eid,
            "username": employee.username,
            "role": employee.role,          # 👈 ONLY HERE
            "branch_id": employee.branch_id,
        }
    })

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def employee_logout(request):
    employee_id = request.data.get("Eid")
    
    if not employee_id:
        return Response({"message": "customer_id is required"}, status=400)
    
    try:
        customer = Employees.objects.get(Eid=employee_id)  # get exact user
        customer.is_logged_in = False
        customer.save(update_fields=["is_logged_in"])
        return Response({"message": "Logged out"})
    except Customer.DoesNotExist:
        return Response({"message": "Customer not found"}, status=404)

@api_view(["POST"])
def customer_register(request):
    data = request.data

    if Customer.objects.filter(phone=data.get("phone")).exists():
        return Response(
            {"error": "Phone already exists"},
            status=status.HTTP_400_BAD_REQUEST
        )

    if data.get("email") and Customer.objects.filter(email=data.get("email")).exists():
        return Response(
            {"error": "Email already exists"},
            status=status.HTTP_400_BAD_REQUEST
        )

    customer = Customer(
        name=data.get("name"),
        phone=data.get("phone"),
        email=data.get("email"),
        password=data.get("password")
    )
    customer.save()

    serializer = CustomerSerializer(customer)
    return Response(
        {"user": serializer.data},
        status=status.HTTP_201_CREATED
    )

@api_view(["POST"])
def customer_login(request): 
    phone = request.data.get("phone")
    password = request.data.get("password")

    try:
        customer = Customer.objects.get(phone=phone)
    except Customer.DoesNotExist:
        return Response({"error": "Invalid credentials"}, status=401)
    
    if not customer.check_password(password):
        return Response({"error": "Invalid password"}, status=401)

    # 🔒 BLOCK if already logged in
    if customer.is_logged_in:
        return Response(
            {"error": "Account already logged in on another device"},
            status=403
        )

    refresh = RefreshToken.for_user(customer)

    customer.is_logged_in = True
    customer.save(update_fields=["is_logged_in"])

    return Response({
        "tokens": {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        },
        "user": {
            "id": customer.Cid,
            "name": customer.name,
            "phone": customer.phone,
        }
    })

@api_view(["POST"])
@authentication_classes([])
@permission_classes([AllowAny])
def customer_logout(request):
    cid = request.data.get("customer_id")
    customer_id = int(cid.replace("TFC", ""))

    if not customer_id:
        return Response({"message": "customer_id is required"}, status=400)
    
    try:
        customer = Customer.objects.get(id=customer_id)  # get exact user
        customer.is_logged_in = False
        customer.save(update_fields=["is_logged_in"])
        return Response({"message": "Logged out"})
    except Customer.DoesNotExist:
        return Response({"message": "Customer not found"}, status=404)
 
@api_view(["POST"])
def create_branch(request):
    serializer = BranchSerializer(data=request.data)
    if serializer.is_valid():
        branch = serializer.save()
        return Response(
            BranchSerializer(branch).data,
            status=status.HTTP_201_CREATED
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["PUT"])
def update_branch(request, id):
    branch = Branch.objects.get(id=id)
    old_required = branch.required_staff

    serializer = BranchSerializer(branch, data=request.data, partial=True)
    if serializer.is_valid():
        branch = serializer.save()

        # 🔥 Auto mark excess staff as NOT WORKING
        if branch.total_staff > branch.required_staff:
            excess = branch.total_staff - branch.required_staff

            idle_staff = Employees.objects.filter(
                branch=branch, is_working=True
            )[:excess]

            idle_staff.update(is_working=False)

        return Response(serializer.data)

    return Response(serializer.errors, status=400)

@api_view(["DELETE"])
def delete_branch(request, id):
    branch = Branch.objects.get(id=id)
    branch.status = "deactivated"
    branch.delete()
    return Response({"message": "Deleted"}, status=204)

@api_view(["GET"])
def excess_staff_list(request):
    staff = Employees.objects.filter(is_working=False,role='staff').select_related("branch")

    return Response([
        {
            "id": e.Eid,
            "name": e.username,
            "role": e.role,
            "branch_id": e.branch.branch_code,
            "branch_name": e.branch.branch_name,
        }
        for e in staff
    ])

@api_view(["POST"])
def assign_excess_staff(request):
    emp_id = request.data.get("employee_id")
    target_branch_id = request.data.get("target_branch_id")

    if not emp_id or not target_branch_id:
        return Response({"error": "employee_id and target_branch_id required"}, status=400)

    try:
        employee = Employees.objects.get(Eid=emp_id)
    except Employees.DoesNotExist:
        return Response({"error": "Employee not found"}, status=404)

    try:
        target_branch = Branch.objects.get(id=target_branch_id)
    except Branch.DoesNotExist:
        return Response({"error": "Branch not found"}, status=404)

    old_branch = employee.branch

    try:
        employee.branch = target_branch
        employee.is_working = True
        employee.save()

        if old_branch:
            old_branch.total_staff = Employees.objects.filter(branch=old_branch, is_working=True).count()
            old_branch.save(update_fields=["total_staff"])

        target_branch.total_staff = Employees.objects.filter(branch=target_branch, is_working=True).count()
        target_branch.save(update_fields=["total_staff"])

        return Response({"success": True})
    except Exception as e:
        print("Assign staff error:", e)
        return Response({"error": str(e)}, status=500)

@api_view(["GET"])
def menu_categories(request):
    categories = MenuItem.objects.values_list("category", flat=True).distinct()
    return Response(list(categories))

@api_view(["GET"])
def admin_menu_list(request):
    search = request.GET.get("search", "").strip()
    food_type = request.GET.get("type", "all").lower()
    is_active_param = request.GET.get("is_active")

    items = MenuItem.objects.all()

    # ✅ Status filter
    if is_active_param == "true":
        items = items.filter(is_active=True)
    elif is_active_param == "false":
        items = items.filter(is_active=False)
    # if is_active not sent → return all (active + inactive)

    # ✅ Veg / Non-veg filter
    if food_type == "veg":
        items = items.filter(is_veg=True)
    elif food_type == "nonveg":
        items = items.filter(is_veg=False)

    # ✅ Search filter
    if search:
        items = items.filter(name__icontains=search)

    serializer = MenuItemSerializer(items, many=True)
    return Response(serializer.data)

@api_view(["POST"])
def admin_menu_create(request):
    serializer = MenuItemSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(["GET"])
def branch_menu_list(request):
    branch_id = request.GET.get("branch_id")
    search = request.GET.get("search", "")
    food_type = request.GET.get("type")  
    category = request.GET.get("category", "all") 

    # ✅ BASE QUERY (all active menu items)
    items = MenuItem.objects.filter(is_active=True)

    # 🥗 Veg / Non-Veg
    if food_type == "veg":
        items = items.filter(is_veg=True)
    elif food_type == "nonveg":
        items = items.filter(is_veg=False)

    if category.lower() != "all":
        items = items.filter(category=category.lower())

    if search:
        items = items.filter(
            name__icontains=search
        )

    data = []

    # 🏪 BRANCH MENU (if branch_id)
    if branch_id:
        branch_items = (
            BranchMenuItem.objects
            .filter(
                branch_id=branch_id,
                is_available=True,
                menu_item__in=items
            )
            .select_related("menu_item")
        )

        for obj in branch_items:
            discont = apply_offer(obj.menu_item.id)
            item = obj.menu_item
            data.append({
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "description": item.description,
                "price": item.price,
                "discontPrice": item.price - discont,
                "discont": discont ,
                "is_veg": item.is_veg,
                "image": item.image.url if item.image else None,
            })

    # FULL MENU (no branch)
    else:
        for item in items:
            discont = apply_offer(item.id)
            data.append({
                "id": item.id,
                "name": item.name,
                "category": item.category,
                "description": item.description,
                "price": item.price ,
                "discontPrice": item.price - discont,
                "discont": discont,
                "is_veg": item.is_veg,
                "image": item.image.url if item.image else None,
            })

    return Response(data)

@api_view(["GET"])
def branch_menu_with_status(request, branch_id):
    items = MenuItem.objects.filter(is_active=True)

    data = []
    for item in items:
        bmi, _ = BranchMenuItem.objects.get_or_create(
            branch_id=branch_id,
            menu_item=item
        )
        data.append({
            "id": item.id,
            "image":request.build_absolute_uri(item.image.url) if item.image else Non,
            "name": item.name,
            "category": item.category,
            "price": item.price,
            "is_available": bmi.is_available
        })

    return Response(data)

@api_view(["PATCH"])
def toggle_menu_availability(request, branch_id, menu_item_id):
    try:
        bmi, _ = BranchMenuItem.objects.get_or_create(
            branch_id=branch_id,
            menu_item_id=menu_item_id
        )
        bmi.is_available = request.data.get("is_available", False)
        bmi.save()

        return Response(
            {"message": "Availability updated"},
            status=status.HTTP_200_OK
        )
    except Exception as e:
        return Response(
            {"error": str(e)},
            status=status.HTTP_400_BAD_REQUEST
        )

@api_view(['GET'])
def model_counts(request):
    data = {
        "branches": Branch.objects.count(),
        "employees": Employees.objects.count(),
        "menuitems": MenuItem.objects.count(),
        "godowns": Godown.objects.count(),
        "items": Item.objects.count(),
        "branch_stock": BranchStock.objects.count(),
        "godown_stock": GodownStock.objects.count(),
        "stock_requests": StockRequest.objects.count(),
        "customers": Customer.objects.count(),
        "orders": Order.objects.count(),
        "order_items": OrderItem.objects.count(),
        "billings": Billing.objects.count(),
        "kitchen_orders": KitchenOrderTicket.objects.count(),
        "expenses": Expense.objects.count(),
        "daily_analytics": DailyAnalytics.objects.count(),
    }

    return Response({
        "status": "success",
        "data": data
    })

@api_view(['GET'])
def admin_all_offers(request):
    eid = request.query_params.get("eid")   # ✅ works only with POST

    if not eid:
        return Response(
            {"detail": "EID is required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    emp = Employees.objects.filter(Eid=eid).first()

    if not emp:
        return Response(
            {"detail": "Employee not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    if emp.role != "admin":
        return Response(
            {"detail": "Unauthorized"},
            status=status.HTTP_403_FORBIDDEN
        )

    offers = Offer.objects.all().order_by("-created_at")
    serializer = OfferSerializer(offers, many=True)

    # ✅ RETURN DATA
    return Response({
        "count": offers.count(),
        "offers": serializer.data
    }, status=status.HTTP_200_OK)

@api_view(["POST"])
def admin_create_offer(request):
    eid = request.data.get("eid")

    admin = Employees.objects.filter(Eid=eid, role="admin").first()
    if not admin:
        return Response({"detail": "Unauthorized"}, status=403)

    serializer = OfferCreateUpdateSerializer(data=request.data)

    if serializer.is_valid():
        serializer.save()
        return Response(
            {"message": "Offer created", "offer": serializer.data},
            status=201
        )

    return Response(serializer.errors, status=400)

@api_view(["PUT"])
def admin_update_offer(request, pk):
    eid = request.data.get("eid")
    emp = Employees.objects.filter(Eid=eid, role="admin").first()

    if not emp:
        return Response({"detail": "Unauthorized"}, status=403)

    offer = Offer.objects.filter(pk=pk).first()
    if not offer:
        return Response({"detail": "Offer not found"}, status=404)

    if offer.start_date <= timezone.now().date():
        return Response(
            {"detail": "Only upcoming offers can be edited"},
            status=400,
        )

    serializer = OfferCreateUpdateSerializer(offer, data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)

    return Response(serializer.errors, status=400)

@api_view(["DELETE"])
def admin_delete_offer(request, pk):
    eid = request.query_params.get("eid")
    emp = Employees.objects.filter(Eid=eid, role="admin").first()

    if not emp:
        return Response({"detail": "Unauthorized"}, status=403)

    offer = Offer.objects.filter(pk=pk).first()
    if not offer:
        return Response({"detail": "Offer not found"}, status=404)

    if offer.start_date <= timezone.now().date():
        return Response(
            {"detail": "Only upcoming offers can be deleted"},
            status=400,
        )

    offer.delete()
    return Response({"detail": "Deleted"}, status=204)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def manager_offers(request):
    if request.user.role != "manager":
        return Response({"detail": "Unauthorized"}, status=403)

    today = timezone.now().date()

    offers = Offer.objects.filter(
        start_date__lte=today
    ).order_by('-start_date')

    serializer = OfferSerializer(offers, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def customer_today_offers(request):
    today = timezone.now().date()

    offers = Offer.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
        is_active=True
    )

    serializer = OfferSerializer(offers, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def branch_list(request):
    branches = Branch.objects.all().order_by("branch_name")
    serializer = BranchSerializer(branches, many=True)
    return Response(serializer.data)

# Optional: Only active branches
@api_view(['GET'])
def active_branch_list(request):
    branches = Branch.objects.all().order_by("branch_name")
    serializer = BranchSerializer(branches, many=True)
    return Response(serializer.data)

@api_view(['GET'])
def Employee_list(request):
    employess = Employees.objects.all()
    serializer = EmplayeeSerializer(employess, many=True, context={'request': request})
    return Response(serializer.data)
   
@api_view(["GET"])
def branch_stock_list(request):
    branch_code = request.GET.get("branch_id")

    try:
        branch = Branch.objects.get(branch_code=branch_code)
    except Branch.DoesNotExist:
        return Response({"error": "Branch not found"}, status=404)

    stocks = BranchStock.objects.filter(branch=branch).select_related("item")

    data = []
    for s in stocks:
        data.append({
            "id": s.id,
            "image": s.item.item_pic.url if s.item.item_pic else None,
            "item": s.item.item_name,
            "quantity": s.quantity,
            "min_level": s.min_level,
            "unit": s.item.unit if hasattr(s.item, "unit") else "",
        })

    return Response(data)


@api_view(["GET"])
def godown_stock_list(request):
    stocks = GodownStock.objects.select_related("item")
    serializer = GodownStockSerializer(stocks, many=True)
    return Response(serializer.data)

@api_view(["POST"])
def create_item_and_godown_stock(request):
    """
    Create a new Item and GodownStock.
    Accepts multipart/form-data for image upload.
    """
    item_name = request.data.get("item_name")
    item_type = request.data.get("item_type")
    category = request.data.get("category")
    price = request.data.get("price") or 0
    quantity = request.data.get("quantity")
    expiry_date = request.data.get("expiry_date")
    unit = request.data.get("unit") or "kg"
    item_pic = request.FILES.get("item_pic")  # image file

    # Required fields validation
    if not item_name or not item_type or not quantity:
        return Response(
            {"error": "item_name, item_type, quantity are required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # 1️⃣ Create Item
        item = Item.objects.create(
            item_name=item_name,
            item_type=item_type,
            category=category,
            price=price,
            item_pic=item_pic,
            unit=unit
        )
    except IntegrityError:
        # Item with same name exists → just add stock to it
        item = Item.objects.get(item_name=item_name)
    
    try:
        # 2️⃣ Create GodownStock
        godown_stock = GodownStock.objects.create(
            item=item,
            quantity=quantity,
            expiry_date=expiry_date
        )
    except Exception as e:
        return Response(
            {"error": f"Failed to create stock: {str(e)}"},
            status=status.HTTP_400_BAD_REQUEST
        )

    return Response({
        "message": "Item and Godown stock created successfully",
        "item_id": item.id,
        "godown_stock_id": godown_stock.id
    }, status=status.HTTP_201_CREATED)

@api_view(["POST"])
def smart_stock_request_view(request):
    branch_id = request.data["branch_id"]
    item_id = request.data["item_id"]
    qty = request.data["quantity"]

    req = create_smart_stock_request(
        Branch.objects.get(id=branch_id),
        Item.objects.get(id=item_id),
        qty
    )

    return Response({
        "message": "Request created",
        "request_type": "branch" if req.to_branch else "godown"
    })

@api_view(["GET"])
def incoming_branch_requests(request, branch_id):
    requests = StockRequest.objects.filter(to_branch_code=branch_id, status="pending")
    return Response([{
        "id": r.branch_code,
        "from_branch": r.from_branch.branch_name,
        "item": r.item.item_name,
        "quantity": r.quantity,
        "expires_at": r.expires_at
    } for r in requests])

@api_view(["POST"])
def respond_branch_request(request, request_id):
    action = request.data.get("action")
    req = StockRequest.objects.get(id=request_id)

    if timezone.now() > req.expires_at:
        return Response({"error": "Request expired"}, status=400)

    if action == "accept":
        approve_inter_branch_request(req)
    else:
        req.status = "rejected"
        req.save()
        # fallback to godown
        StockRequest.objects.create(
            from_branch=req.from_branch,
            item=req.item,
            quantity=req.quantity,
            from_godown=True
        )

    return Response({"message": "Updated"})

@api_view(["POST"])
def approve_godown_request_view(request, request_id):
    req = StockRequest.objects.get(id=request_id)
    approve_godown_request(req)
    return Response({"message": "Approved"})

@api_view(["POST"])
def handle_expired_requests(request):
    handle_stock_request_timeouts()
    return Response({"message": "Checked expired requests"})

@api_view(["GET"])
def branch_dashboard(request):
    branch_id = request.GET.get("branch_id")

    if not branch_id:
        return Response({"error": "branch_id required"}, status=400)

    try:
        branch = Branch.objects.get(id=branch_id)
    except Branch.DoesNotExist:
        return Response({"error": "Branch not found"}, status=404)

    today = timezone.now().date()

    # 👥 Employees working in this branch
    employees_count = Employees.objects.filter(
        branch=branch,
        is_working=True,
        is_active=True
    ).count()

    # 🛒 Orders completed today
    completed_orders = Order.objects.filter(
        branch=branch,
        status="delivered",
        created_at__date=today
    ).count()

    # 📦 Branch Stock Summary
    stock_items = BranchStock.objects.filter(branch=branch)
    stock_summary = stock_items.aggregate(
        total_quantity=models.Sum("quantity")
    )["total_quantity"] or 0

    # 🎉 Today's Active Offers
    offers = Offer.objects.filter(
        start_date__lte=today,
        end_date__gte=today,
        is_active=True
    )
    offers_data = OfferSerializer(offers, many=True).data

    return Response({
        "branch": {
            "id": branch.id,
            "code": branch.branch_code,
            "name": branch.branch_name,
            "city": branch.city,
            "staff_required": branch.required_staff,
            "staff_working": branch.total_staff,
        },
        "counts": {
            "employees": employees_count,
            "completed_orders": completed_orders,
            "stock_quantity": stock_summary,
        },
        "offers": offers_data
    })

@api_view(["GET"])
def branches_stock_summary(request):
    branches = Branch.objects.all()
    data = []
    for b in branches:
        total = BranchStock.objects.filter(branch=b).aggregate(total=models.Sum('quantity'))['total'] or 0
        data.append({
            "branch_id": b.branch_code,
            "branch_name": b.branch_name,
            "total_items": total
        })
    return Response(data)

@api_view(["GET"])
def branch_employees_list(request):
    branch_id = request.GET.get("branch_id")
    if not branch_id:
        return Response({"error": "branch_id required"}, status=400)

    employees = Employees.objects.filter(branch_id=branch_id)
    serializer = BranchEmployeeSerializer(employees, many=True)
    return Response(serializer.data)

@api_view(["POST"])
def branch_add_employee(request):
    # Only staff can be added by branch_manager
    data = request.data
    data['role'] = 'staff'  # force role to staff

    serializer = BranchEmployeeSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Staff added", "employee": serializer.data}, status=201)
    return Response(serializer.errors, status=400)

@api_view(["PATCH"])
def branch_edit_employee(request, staff_id):
    try:
        employee = Employees.objects.get(id=staff_id)
    except Employees.DoesNotExist:
        return Response({"error": "Employee not found"}, status=404)

    if employee.role != "staff":
        return Response({"error": "Cannot edit non-staff"}, status=403)

    serializer = BranchEmployeeSerializer(employee, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response({"message": "Updated", "employee": serializer.data})
    return Response(serializer.errors, status=400)

@api_view(["DELETE"])
def branch_delete_employee(request, staff_id):
    try:
        employee = Employees.objects.get(id=staff_id)
    except Employees.DoesNotExist:
        return Response({"error": "Employee not found"}, status=404)

    if employee.role != "staff":
        return Response({"error": "Cannot delete non-staff"}, status=403)

    employee.delete()
    return Response({"message": "Deleted"})

@api_view(["PATCH"])
def branch_toggle_working(request, staff_id):
    try:
        employee = Employees.objects.get(id=staff_id)
    except Employees.DoesNotExist:
        return Response({"error": "Employee not found"}, status=404)

    if employee.role != "staff":
        return Response({"error": "Cannot toggle non-staff"}, status=403)

    employee.is_working = request.data.get("is_working", not employee.is_working)
    employee.save()
    return Response({"message": "Updated", "is_working": employee.is_working})

@api_view(["POST"])
def add_to_cart(request):
    cid = request.data.get("id")
    customer_id = int(cid.replace("TFC", ""))
    menu_item_id = request.data.get("menu_item_id")
    quantity = int(request.data.get("quantity", 1))

    if quantity < 1:
        return Response({"error": "Invalid quantity"}, status=400)

    cart, _ = Cart.objects.get_or_create(customer_id=customer_id)

    menu_item = MenuItem.objects.get(id=menu_item_id)

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        menu_item=menu_item,
        defaults={
            "quantity": quantity,
            "price": menu_item.price,   # REQUIRED
        }
    )

    if not created:
        cart_item.quantity += quantity
        cart_item.save()

    return Response({"message": "Item added to cart"})

@api_view(["GET"])
def view_cart(request):
    cid = request.query_params.get("customer_id")
    customer_id = int(cid.replace("TFC", ""))
    if not customer_id:
        return Response({"error": "customer_id required"}, status=400)

    cart = (
        Cart.objects
        .filter(customer_id=customer_id)
        .select_related("branch")
        .prefetch_related("items__menu_item")
        .first()
    )

    if not cart:
        return Response({
            "items": [],
            "subtotal": 0,
            "cgst": 0,
            "sgst": 0,
            "total": 0
        })

    items_data = []
    subtotal = Decimal("0.00")
    total_discount = Decimal("0.00")

    for item in cart.items.all():
        offer = apply_offer(item.menu_item.id)
        total_discount += offer
        item_total = (item.price - offer) * item.quantity
        subtotal += item_total

        items_data.append({
            "menu_item_id": item.menu_item.id,
            "discont": apply_offer(item.menu_item.id),
            "name": item.menu_item.name,
            "price": float(item.price),
            "quantity": item.quantity,
            "total": float(item_total),
            "image": item.menu_item.image.url if item.menu_item.image else None
        })

    cgst = (subtotal * Decimal("0.025")).quantize(Decimal("0.01"))
    sgst = (subtotal * Decimal("0.025")).quantize(Decimal("0.01"))
    total = (subtotal + cgst + sgst).quantize(Decimal("0.01"))


    return Response({
        "items": items_data,
        "subtotal": float(subtotal),
        "cgst": float(cgst),
        "sgst": float(sgst),
        "total": float(total),
        "total_discount" : total_discount
    })

@api_view(["PATCH"])
def update_cart_quantity(request):
    cid = request.data.get("customer_id")
    customer_id = int(cid.replace("TFC", ""))
    menu_item_id = request.data.get("menu_item_id")
    quantity = int(request.data.get("quantity"))

    if quantity < 1:
        CartItem.objects.filter(
            cart__customer_id=customer_id,
            menu_item_id=menu_item_id
        ).delete()
        return Response({"message": "Item removed"})

    CartItem.objects.filter(
        cart__customer_id=customer_id,
        menu_item_id=menu_item_id
    ).update(quantity=quantity)

    return Response({"message": "Quantity updated"})

@api_view(["POST"])
@transaction.atomic
def place_order(request):
    Bid = request.data.get("Bid")
    cid = request.data.get("customer_id")
    customer_id = int(cid.replace("TFC", ""))
    if not customer_id:
        return Response({"error": "customer_id required"}, status=400)

    branch = Branch.objects.get(id=Bid)
    cart = (
        Cart.objects
        .filter(customer_id=customer_id)
        .prefetch_related("items__menu_item")
        .first()
    )
    cart.branch=branch
    cart.save()

    if not cart or not cart.items.exists():
        return Response({"error": "Cart is empty"}, status=400)

    subtotal = Decimal("0.00")
    total_discount = Decimal("0.00")
    for item in cart.items.all():
        discount = Decimal(apply_offer(item.menu_item.id))
        item_price_after_discount = item.price - discount

        if item_price_after_discount < 0:
            item_price_after_discount = Decimal("0.00")

        subtotal += item_price_after_discount * item.quantity
        total_discount += discount * item.quantity

    cgst = (subtotal * Decimal("0.025")).quantize(Decimal("0.01"))
    sgst = (subtotal * Decimal("0.025")).quantize(Decimal("0.01"))
    total = (subtotal + cgst + sgst).quantize(Decimal("0.01"))

    # ✅ Create Order
    order = Order.objects.create(
        customer_id=customer_id,
        branch=cart.branch,
        subtotal=subtotal,
        gst_amount=cgst + sgst,
        total_amount=total,
        status="pending"
    )

    tixe = TiexCollect.objects.create(
        gst= cgst + sgst,
        branch = Branch.objects.get(id=Bid),
    )
    tixe.save()

    # ✅ Create Order Items
    for item in cart.items.all():
        OrderItem.objects.create(
            order=order,
            menu_item=item.menu_item,
            quantity=item.quantity,
            price=item.price,
            discount = apply_offer(item.menu_item.id)
        )

    # ✅ Update Branch Sales
    cart.branch.sales = (Decimal(cart.branch.sales + total).quantize(Decimal("0.01")))
    cart.branch.save(update_fields=["sales"])

    # ✅ Clear Cart
    cart.items.all().delete()
    cart.delete()   

    return Response({
        "message": "Order placed successfully",
        "order_id": order.id,
        "subtotal": float(subtotal),
        "cgst": float(cgst),
        "sgst": float(sgst),
        "total": float(total)
    }, status=201)

@api_view(["GET"])
@permission_classes([AllowAny])
def current_orders(request):
    cid = request.GET.get("customer_id")
    customer_id = int(cid.replace("TFC", ""))

    if not customer_id:
        return Response(
            {"error": "customer_id is required"},
            status=400
        )

    orders = Order.objects.filter(
        customer_id=customer_id,
        status__in=["pending", "accepted", "preparing", "ready"]
    ).order_by("-created_at")
    data = OrderSerializer(orders, many=True).data

    return Response(data)

@api_view(["GET"])
def order_history(request):
    cid = request.GET.get("customer_id")
    customer_id = int(cid.replace("TFC", ""))
    if not customer_id:
        return Response(
            {"error": "customer_id is required"},
            status=400
        )
    
    orders = Order.objects.filter(
        customer_id=customer_id,
        status__in=["completed", "cancelled"]
    ).order_by("-created_at")

    return Response(OrderSerializer(orders, many=True).data)

@api_view(["POST"])
def cancel_order(request):
    order_id = request.data.get("order_id")
    cid = request.data.get("customer_id")
    print(cid)
    customer_id = int(cid.replace("TFC", ""))

    if not order_id or not customer_id:
        return Response(
            {"error": "order_id and customer_id are required"},
            status=400
        )

    try:
        order = Order.objects.get(
            id=order_id,
            customer__id=customer_id,
            status="pending"
        )
    except Order.DoesNotExist:
        return Response(
            {"error": "Order cannot be cancelled"},
            status=400
        )

    order.delete()
    return Response({"message": "Order deleted successfully"})

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def chef_status(request):
    chef = request.user

    if chef.role != "staff":
        return Response({"error": "Not a chef"}, status=403)

    return Response({
        "is_working": chef.is_working
    })

@api_view(["GET"])
def kitchen_orders(request):
    branch_id = request.GET.get("branch_id")

    if not branch_id :
        return Response({"branch_id" : "required id"})

    orders = Order.objects.filter(
        branch__branch_code=branch_id,
        status__in=["pending", "accepted", "preparing", "ready"]
    ).order_by("created_at")

    return Response(OrderSerializer(orders, many=True).data)

@api_view(["GET"])
def chef_current_order(request):
    Eid = request.GET.get("eid")
    order = Order.objects.filter(
        assigned_chef__Eid=Eid,
        status="preparing"
    ).first()

    if not order:
        return Response(None)

    return Response(ChefOrderSerializer(order).data)

@api_view(["GET"])
def chef_branch_ingredients(request):
    chef = request.GET.get('branchCode')
    print(chef)
    if not chef :
        return Response({'message': chef})

    stocks = BranchStock.objects.filter(
        branch__branch_code=chef
    ).select_related("item")

    return Response([
        {
            "item_id": s.item.id,
            "name": s.item.item_name,
            "available_qty": s.quantity,
            "unit": s.item.unit
        }
        for s in stocks
    ])

@api_view(["POST"])
@transaction.atomic
def submit_ingredient_usage(request):
    Eid = request.data.get("Eid")
    Bid = request.data.get("Bid")
    total = request.data.get("total")
    order_id = request.data.get("order_id")
    ingredients = request.data.get("ingredients", [])

    order = Order.objects.select_for_update().get(
        id=order_id,
        assigned_chef__Eid=Eid,
        status="preparing"
    )

    chef = Employees.objects.select_for_update().get(Eid=Eid)
    branch = Branch.objects.select_for_update().get(branch_code = Bid)
    for ing in ingredients:
        item_id = ing["item_id"]
        qty = Decimal(ing["quantity"])

        stock = BranchStock.objects.select_for_update().get(
            branch__branch_code=Bid,
            item_id=item_id
        )

        if stock.quantity < qty:
            raise Exception(
                f"Insufficient stock for {stock.item.item_name}"
            )

        # 🔻 Deduct stock
        stock.quantity -= qty
        stock.save()

        # 📝 Save usage
        OrderIngredientUsage.objects.create(
            order=order,
            item_id=item_id,
            quantity_used=qty
        )

    # ✅ Mark order ready
    order.status = "completed"
    order.save()

    branch.sales += Decimal(total)
    branch.save()

    chef.is_working = True
    chef.save()

    return Response({
        "message": "Ingredients submitted & stock updated"
    })

@api_view(["GET"])
def pending_orders(request):
    branch_id = request.GET.get("branch_id")

    orders = Order.objects.filter(
        branch__branch_code=branch_id,
        status="pending"
    ).order_by("created_at")

    data = []
    for index, o in enumerate(orders):
        data.append({
            "order_id": o.id,
            "order_code": o.order_code,
            "time": o.created_at,
            "customer_id": o.customer.Cid,
            "can_accept": index == 0   # 👈 only first order
        })

    return Response(data)

@api_view(["POST"])
def accept_order(request):
    order_id = request.data.get("order_id")
    employee_id = request.data.get("Eid")

    if not order_id or not employee_id:
        return Response(
            {"error": "order_id and Eid are required"},
            status=status.HTTP_400_BAD_REQUEST
        )

    # 🔍 Get chef
    try:
        chef = Employees.objects.get(Eid=employee_id, role="chef")
    except Employees.DoesNotExist:
        return Response(
            {"error": "Chef not found"},
            status=status.HTTP_404_NOT_FOUND
        )

    # 🔍 Check if chef already has an active order
    active_order_exists = Order.objects.filter(
        assigned_chef=chef
    ).exclude(
        status__in=["completed", "cancelled"]
    ).exists()

    if active_order_exists:
        return Response(
            {
                "error": "Chef already has an active order. Please complete or cancel it first."
            },
            status=status.HTTP_400_BAD_REQUEST
        )

    # 🔍 Get order
    try:
        order = Order.objects.get(id=order_id, status="pending")
    except Order.DoesNotExist:
        return Response(
            {"error": "Order not found or already processed"},
            status=status.HTTP_404_NOT_FOUND
        )

    # ✅ Assign order
    order.status = "preparing"
    order.assigned_chef = chef
    order.save()

    return Response(
        {"message": "Order accepted and assigned to chef"},
        status=status.HTTP_200_OK
    )

@api_view(['GET'])
def chef_completed_orders(request):
    Eid = request.GET.get("Eid")
    if not Eid:
        return Response(
            {"error": "Eid is required"},
            status=400
        )
    
    orders = Order.objects.filter(
        assigned_chef__Eid=Eid,
        status__in=["completed"]
    ).order_by("-created_at")

    return Response(OrderSerializer(orders, many=True).data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def complete_order(request):
    order_id = request.data.get('order_id')
    chef = request.user

    order = Order.objects.get(id=order_id, assigned_chef=chef)

    order.status = 'ready'
    order.save()

    chef.is_working = True
    chef.save()

    return Response({"message": "Order marked as ready"})

@api_view(["DELETE"])
def remove_cart_item(request):
    cid = request.data.get("customer_id")
    customer_id = int(cid.replace("TFC", ""))
    menu_item_id = request.data.get("menu_item_id")

    if not customer_id or not menu_item_id:
        return Response(
            {"error": "customer_id and menu_item_id required"},
            status=400
        )

    cart = Cart.objects.filter(customer_id=customer_id).first()
    if not cart:
        return Response({"error": "Cart not found"}, status=404)

    CartItem.objects.filter(
        cart=cart,
        menu_item_id=menu_item_id
    ).delete()

    return Response({"message": "Item removed"})

@api_view(["DELETE"])
def clear_cart(request):
    cid = request.data.get("customer_id")
    customer_id = int(cid.replace("TFC",""))

    if not customer_id:
        return Response({"error": "customer_id required"}, status=400)

    cart = Cart.objects.filter(customer_id=customer_id).first()
    if cart:
        cart.items.all().delete()
        cart.delete()

    return Response({"message": "Cart cleared"})

@api_view(["GET"])
def global_summary(request):
    today = now().date()

    # Today
    today_orders = Order.objects.filter(
        created_at__date=today
    )

    today_sales = today_orders.aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0.00")

    today_gst = TiexCollect.objects.filter(
        created_at__date=today
    ).aggregate(
        total=Sum("gst")
    )["total"] or Decimal("0.00")

    # THIS WEEK
    week_start = today - timedelta(days=today.weekday())

    week_orders = Order.objects.filter(
        status="completed",
        created_at__date__gte=week_start,
        created_at__date__lte=today
    )

    week_sales = week_orders.aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0.00")

    week_gst = TiexCollect.objects.filter(
        created_at__date__gte=week_start,
        created_at__date__lte=today
    ).aggregate(
        total=Sum("gst")
    )["total"] or Decimal("0.00")

    #THIS MONTH
    month_start = today.replace(day=1)

    month_orders = Order.objects.filter(
        status="completed",
        created_at__date__gte=month_start,
        created_at__date__lte=today
    )

    month_sales = month_orders.aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0.00")

    month_gst = TiexCollect.objects.filter(
        created_at__date__gte=month_start,
        created_at__date__lte=today
    ).aggregate(
        total=Sum("gst")
    )["total"] or Decimal("0.00")

    # PREVIOUS MONTH
    first_day_this_month = month_start
    last_day_prev_month = first_day_this_month - timedelta(days=1)
    first_day_prev_month = last_day_prev_month.replace(day=1)

    prev_month_orders = Order.objects.filter(
        status="completed",
        created_at__date__gte=first_day_prev_month,
        created_at__date__lte=last_day_prev_month
    )

    prev_month_sales = prev_month_orders.aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0.00")

    prev_month_gst = TiexCollect.objects.filter(
        created_at__date__gte=first_day_prev_month,
        created_at__date__lte=last_day_prev_month
    ).aggregate(
        total=Sum("gst")
    )["total"] or Decimal("0.00")

    return Response({
        "today": {
            "date": today,
            "total_orders": today_orders.count(),
            "total_sales": today_sales,
            "total_gst": today_gst,
        },
        "this_week": {
            "from": week_start,
            "to": today,
            "total_orders": week_orders.count(),
            "total_sales": week_sales,
            "total_gst": week_gst,
        },
        "this_month": {
            "from": month_start,
            "to": today,
            "total_orders": month_orders.count(),
            "total_sales": month_sales,
            "total_gst": month_gst,
        },
        "previous_month": {
            "from": first_day_prev_month,
            "to": last_day_prev_month,
            "total_orders": prev_month_orders.count(),
            "total_sales": prev_month_sales,
            "total_gst": prev_month_gst,
        }
    })

@api_view(["GET"])
def branch_summary(request):
    branch_id = request.GET.get("branch_id")

    if not branch_id:
        return Response({"error": "branch_id is required"}, status=400)

    try:
        branch = Branch.objects.get(id=branch_id)
    except Branch.DoesNotExist:
        return Response({"error": "Branch not found"}, status=404)

    today = now().date()

    # TODAY
    today_orders = Order.objects.filter(
        branch=branch,
        created_at__date=today
    )

    today_sales = today_orders.aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0.00")

    today_gst = TiexCollect.objects.filter(
        branch=branch,
        created_at__date=today
    ).aggregate(
        total=Sum("gst")
    )["total"] or Decimal("0.00")

    # THIS WEEK
    week_start = today - timedelta(days=today.weekday())

    week_orders = Order.objects.filter(
        branch=branch,
        status="completed",
        created_at__date__gte=week_start,
        created_at__date__lte=today
    )

    week_sales = week_orders.aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0.00")

    week_gst = TiexCollect.objects.filter(
        branch=branch,
        created_at__date__gte=week_start,
        created_at__date__lte=today
    ).aggregate(
        total=Sum("gst")
    )["total"] or Decimal("0.00")

    # THIS MONTH
    month_start = today.replace(day=1)

    month_orders = Order.objects.filter(
        branch=branch,
        status="completed",
        created_at__date__gte=month_start,
        created_at__date__lte=today
    )

    month_sales = month_orders.aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0.00")

    month_gst = TiexCollect.objects.filter(
        branch=branch,
        created_at__date__gte=month_start,
        created_at__date__lte=today
    ).aggregate(
        total=Sum("gst")
    )["total"] or Decimal("0.00")

    # PREVIOUS MONTH
    first_day_this_month = month_start
    last_day_prev_month = first_day_this_month - timedelta(days=1)
    first_day_prev_month = last_day_prev_month.replace(day=1)

    prev_month_orders = Order.objects.filter(
        branch=branch,
        status="completed",
        created_at__date__gte=first_day_prev_month,
        created_at__date__lte=last_day_prev_month
    )

    prev_month_sales = prev_month_orders.aggregate(
        total=Sum("total_amount")
    )["total"] or Decimal("0.00")

    prev_month_gst = TiexCollect.objects.filter(
        branch=branch,
        created_at__date__gte=first_day_prev_month,
        created_at__date__lte=last_day_prev_month
    ).aggregate(
        total=Sum("gst")
    )["total"] or Decimal("0.00")

    return Response({
        "branch": {
            "id": branch.id,
            "code": branch.branch_code,
            "name": branch.branch_name,
        },
        "today": {
            "date": today,
            "total_orders": today_orders.count(),
            "total_sales": today_sales,
            "total_gst": today_gst,
        },
        "this_week": {
            "from": week_start,
            "to": today,
            "total_orders": week_orders.count(),
            "total_sales": week_sales,
            "total_gst": week_gst,
        },
        "this_month": {
            "from": month_start,
            "to": today,
            "total_orders": month_orders.count(),
            "total_sales": month_sales,
            "total_gst": month_gst,
        },
        "previous_month": {
            "from": first_day_prev_month,
            "to": last_day_prev_month,
            "total_orders": prev_month_orders.count(),
            "total_sales": prev_month_sales,
            "total_gst": prev_month_gst,
        }
    })

@api_view(["GET"])
def leading_branch(request):
    branches = Branch.objects.all()

    branch_sales = []
    today = date.today()

    # Current month range
    current_month_start = make_aware(datetime(today.year, today.month, 1))
    current_month_end = make_aware(datetime(today.year, today.month, monthrange(today.year, today.month)[1], 23, 59, 59))
    current_month_name = month_name[today.month]

    # Previous month range
    prev_month = today.month - 1 or 12
    prev_year = today.year if today.month > 1 else today.year - 1
    prev_month_start = make_aware(datetime(prev_year, prev_month, 1))
    prev_month_end = make_aware(datetime(prev_year, prev_month, monthrange(prev_year, prev_month)[1], 23, 59, 59))
    prev_month_name = month_name[prev_month]

    for b in branches:
        manager = Employees.objects.filter(branch__branch_code=b.branch_code, role="branch_manager").first()

        prev_sales = b.order_set.filter(
            created_at__range=(prev_month_start, prev_month_end)
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        current_sales = b.order_set.filter(
            created_at__range=(current_month_start, current_month_end)
        ).aggregate(total=Sum('total_amount'))['total'] or 0

        branch_sales.append({
            "branch_name": b.branch_name,
            "branch_code": b.branch_code,
            "branch_manager": manager.username if manager else None,
            "previous_month_name": prev_month_name,
            "previous_month_sales": float(prev_sales),
            "current_month_name": current_month_name,
            "current_month_sales": float(current_sales)
        })

    # Sort descending by current month sales
    leading = sorted(branch_sales, key=lambda x: x["current_month_sales"], reverse=True)

    if leading:
        return Response(leading[0])
    return Response({"error": "No branches found"}, status=404)


@api_view(['GET'])
def send_gst_email_api(request):
    today = now()

    # Only allow execution on 1st day
    if today.day != 1:
        return Response({"message": "Not scheduled day"}, status=200)

    success, data = send_monthly_gst_email()
    send_monthly_gst_whatsapp()

    return Response({"status": "GST Sent"})

@api_view(["GET"])
def send_whatsapp(request):
    try:
        send_monthly_gst_whatsapp()
        return Response({"status": "success", "message": "WhatsApp message sent"})
    except Exception as e:
        return Response({"status": "error", "error": str(e)}, status=500)
