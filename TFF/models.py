from django.db import models
from django.contrib.auth.hashers import make_password, check_password, identify_hasher
from django.utils.timezone import now
from decimal import Decimal
from django.db.models import Q

class Employees(models.Model):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('branch_manager', 'Branch Manager'),
        ('staff', 'Staff'),
        ('chef', 'Chef'),
    )

    profile_pic = models.ImageField(
        upload_to='employees/profile_pics/',
        null=True,
        blank=True
    )
    Eid = models.CharField(max_length=10, unique=True, editable=False)
    username = models.CharField(max_length=100, unique=True)
    password = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    branch = models.ForeignKey(
        'Branch', on_delete=models.SET_NULL, null=True, blank=True
    )
    phone = models.CharField(max_length=15, unique=True)
    email = models.EmailField()
    work_exprence = models.IntegerField(default=0)
    is_working = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_logged_in = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['branch'],
                condition=Q(role='branch_manager'),
                name='unique_branch_manager_per_branch'
            )
        ]

    def save(self, *args, **kwargs):
        # Generate Employee ID
        if not self.Eid:
            last_emp = Employees.objects.order_by('-id').first()
            if last_emp and last_emp.Eid:
                last_number = int(last_emp.Eid.replace('TFEM', ''))
                new_number = last_number + 1
            else:
                new_number = 1
            self.Eid = f"TFEM{new_number:03d}"

        # 🔐 Hash password ONLY if it's not already hashed
        if not self.password.startswith('pbkdf2_'):
            self.password = make_password(self.password)

        super().save(*args, **kwargs)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def __str__(self):
        if self.branch:
            return f"{self.username} ({self.branch.branch_name})"
        return self.username

class Customer(models.Model):
    id = models.BigAutoField(primary_key=True)  # DB handles concurrency
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=15)
    email = models.EmailField(null=True, blank=True)
    password = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    is_logged_in = models.BooleanField(default=False)

    @property
    def Cid(self):
        digits = max(3, len(str(self.id)))
        return f"TFC{self.id:0{digits}d}"
    
    def save(self, *args, **kwargs):
        """
        Hash password ONLY if it's raw.
        Safe against double hashing.
        """
        try:
            identify_hasher(self.password)  # already hashed
        except ValueError:
            self.password = make_password(self.password)

        super().save(*args, **kwargs)

    def check_password(self, raw_password):
        return check_password(raw_password, self.password)

    def __str__(self):
        return self.name

class Branch(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('renovating', 'Renovating'),
        ('deactivated', 'Deactivated'),
    )

    branch_code = models.CharField(max_length=10, unique=True, editable=False)
    branch_name = models.CharField(max_length=150)
    address = models.TextField()
    sales = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    city = models.CharField(max_length=100)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    phone = models.CharField(max_length=15)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='active'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    total_staff = models.PositiveIntegerField(default=0)
    required_staff = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        # Generate branch_code only once
        if not self.branch_code:
            last_branch = Branch.objects.order_by('-id').first()
            if last_branch and last_branch.branch_code:
                last_number = int(last_branch.branch_code.replace('TFFB', ''))
                new_number = last_number + 1
            else:
                new_number = 1

            self.branch_code = f"TFFB{new_number:03d}"

        super().save(*args, **kwargs)

    @property
    def not_needed_staff(self):
        return max(self.total_staff - self.required_staff, 0)

    @property
    def shortage_staff(self):
        return max(self.required_staff - self.total_staff, 0)

    def __str__(self):
        return f"{self.branch_code} - {self.branch_name}"

class MenuItem(models.Model):
    ROLE_CATEGORY = (
        ('starter', 'Staeter'),
        ('rice', 'Rice'),
        ('biryani', 'Biryani'),
        ('currie', 'Currie'),
        ("tandoori", 'Tandoori'),
        ('fastfood', 'Fast Food'),
        ('tiffin', 'Tiffin'),
        ('dessert', 'Dessert'),
        ('beverages', 'Beverages'),
    )
    name = models.CharField(max_length=150)
    category = models.CharField(max_length=50, choices=ROLE_CATEGORY)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to="menu/", null=True, blank=True)
    is_veg = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)  # admin global ON/OFF
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class BranchMenuItem(models.Model):
    branch = models.ForeignKey(
        "Branch", on_delete=models.CASCADE
    )
    menu_item = models.ForeignKey(
        MenuItem, on_delete=models.CASCADE
    )
    is_available = models.BooleanField(default=False)

    class Meta:
        unique_together = ("branch", "menu_item")

    def __str__(self):
        return f"{self.branch.branch_name} - {self.menu_item.name}"

class Offer(models.Model):
    OFFER_TYPE_CHOICES = (
        ('upto', 'Upto Percentage'),
        ('flat', 'Flat Amount'),
    )

    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)

    menu_item = models.ForeignKey(
        MenuItem, on_delete=models.CASCADE, related_name="offers"
    )

    offer_type = models.CharField(max_length=20, choices=OFFER_TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=5, decimal_places=2)

    start_date = models.DateField()
    end_date = models.DateField()

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.menu_item.name}) ({self.start_date})"

class Godown(models.Model):
    godown_name = models.CharField(max_length=150)
    address = models.TextField()
    phone = models.CharField(max_length=15)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.godown_name

class Item(models.Model):
    UNIT_CHOICES = (
        ('kg', 'Kilogram'),
        ('ltr', 'Litre'),
        ('pcs', 'Pieces'),
    )
    ITEM_TYPE_CHOICES = (
        ('menu_item', 'Menu Item'),
        ('raw_material', 'Raw Material'),
    )
    item_pic = models.ImageField(
        upload_to='items/pics/',
        null=True,
        blank=True
    )
    item_name = models.CharField(max_length=150, unique=True)
    item_type = models.CharField(max_length=20, choices=ITEM_TYPE_CHOICES)
    category = models.CharField(max_length=100)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES)
    price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.item_name

class BranchStock(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    min_level = models.DecimalField(max_digits=10, decimal_places=2)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('branch', 'item')

    def __str__(self):
        return f"{self.branch} - {self.item}"

class GodownStock(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, unique=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    expiry_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_expired(self):
        from django.utils.timezone import now
        return self.expiry_date and self.expiry_date < now().date()
    
    def __str__(self):
        return f"Godown - {self.item}"

class StockRequest(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('timeout', 'Timeout'),
    )

    from_branch = models.ForeignKey(
        Branch, related_name='stock_requests_from', on_delete=models.CASCADE
    )
    to_branch = models.ForeignKey(
        Branch,
        related_name='stock_requests_to',
        null=True,
        blank=True,
        on_delete=models.CASCADE
    )

    from_godown = models.BooleanField(default=False)

    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending'
    )

    expires_at = models.DateTimeField(null=True, blank=True)  # 🔥 15 min logic
    created_at = models.DateTimeField(auto_now_add=True)

class Order(models.Model):
    ORDER_STATUS = (
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("preparing", "Preparing"),
        ("ready", "Ready"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    )
    order_code = models.CharField(
        max_length=30,
        unique=True,
        editable=False,
        db_index=True
    )
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)
    branch = models.ForeignKey("Branch", on_delete=models.CASCADE)

    assigned_chef = models.ForeignKey(
        "Employees",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        limit_choices_to={"role": "chef"},
        related_name="orders"
    )

    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)

    status = models.CharField(max_length=20, choices=ORDER_STATUS, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.order_code:
            today = now().strftime("%Y%m%d")

            last_order = Order.objects.filter(
                order_code__startswith=f"TFFORD{today}"
            ).order_by("-id").first()

            if last_order:
                last_number = int(last_order.order_code.split("-")[-1])
                next_number = last_number + 1
            else:
                next_number = 1

            self.order_code = f"TFFORD{today}-{next_number:04d}"

        super().save(*args, **kwargs)

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name="items", on_delete=models.CASCADE)
    menu_item = models.ForeignKey("MenuItem", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)

class Billing(models.Model):
    PAYMENT_MODE_CHOICES = (
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('upi', 'UPI'),
    )

    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Bill #{self.id}"

class KitchenOrderTicket(models.Model):
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('cooking', 'Cooking'),
        ('ready', 'Ready'),
    )

    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"KOT #{self.id}"

class Expense(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    description = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    expense_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.description

class DailyAnalytics(models.Model):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)
    date = models.DateField()
    total_sales = models.DecimalField(max_digits=10, decimal_places=2)
    total_expense = models.DecimalField(max_digits=10, decimal_places=2)
    net_profit = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('branch', 'date')

    def __str__(self):
        return f"{self.branch} - {self.date}"

class Cart(models.Model):
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)
    branch = models.ForeignKey("Branch", on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, related_name="items", on_delete=models.CASCADE)
    menu_item = models.ForeignKey("MenuItem", on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

class CustomerOrderHistory(models.Model):
    customer = models.ForeignKey("Customer", on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

class BranchOrderHistory(models.Model):
    branch = models.ForeignKey("Branch", on_delete=models.CASCADE)
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)

class OrderIngredientUsage(models.Model):
    order = models.ForeignKey(
        Order, related_name="ingredient_usages",
        on_delete=models.CASCADE
    )
    item = models.ForeignKey(Item, on_delete=models.CASCADE)  # vegetable / ingredient
    quantity_used = models.DecimalField(max_digits=10, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("order", "item")

    def __str__(self):
        return f"{self.order.order_code} - {self.item.item_name}"

class TiexCollect(models.Model):
    gst = models.DecimalField(max_digits=10, decimal_places=2)
    branch = models.ForeignKey("Branch", on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.branch}"
