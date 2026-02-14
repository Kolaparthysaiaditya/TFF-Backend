from rest_framework import serializers
from django.utils import timezone
from .models import *

class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = "__all__"
        read_only_fields = ("branch_code", "created_at")

class EmplayeeSerializer(serializers.ModelSerializer):
    profile_pic = serializers.ImageField(use_url=True, required=False)
    branch = BranchSerializer(read_only=True)
    class Meta:
        model = Employees
        fields = "__all__"

class CustomerSerializer(serializers.ModelSerializer):
    Cid = serializers.ReadOnlyField()

    class Meta:
        model = Customer
        fields = ['Cid', 'name', 'phone', 'email', 'created_at']
    
class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = [
            "id",
            "name",
            "category",
            "description",
            "price",
            "image",
        ]

class OfferSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    offer_status = serializers.SerializerMethodField()
    display_text = serializers.SerializerMethodField()
    item_name = serializers.SerializerMethodField()
    item_description = serializers.SerializerMethodField()

    class Meta:
        model = Offer
        fields = "__all__"
    
    def get_item_name(self, obj):
        return obj.menu_item.name if obj.menu_item else None
    
    def get_item_description(self, obj):
        return obj.menu_item.description if obj.menu_item else none

    def get_image(self, obj):
        if obj.menu_item.image:
            return obj.menu_item.image.url
        return None

    def get_can_edit(self, obj):
        today = timezone.localdate()
        print(today)
        return obj.end_date > today  # Only today & future offers editable

    def get_offer_status(self, obj):
        today = timezone.now().date()
        if obj.end_date < today:
            return "expired"
        elif obj.start_date > today:
            return "upcoming"
        return "active"
    
    def get_display_text(self, obj):
        if obj.offer_type == "percentage":
            return f"{obj.discount_value}% OFF"
        if obj.offer_type == "upto":
            return f"UPTO {obj.discount_value}% OFF"
        if obj.offer_type == "flat":
            return f"₹ {obj.discount_value} OFF"
        return ""

    def validate(self, data):
        if data['end_date'] < data['start_date']:
            raise serializers.ValidationError(
                "End date cannot be before start date"
            )
        return data
    
class OfferCreateUpdateSerializer(serializers.ModelSerializer):
    menu_item_name = serializers.CharField(
        source="menu_item.name", read_only=True
    )
    class Meta:
        model = Offer
        fields = [
            "title",
            "description",
            "menu_item",
            "menu_item_name",
            "offer_type",
            "discount_value",
            "start_date",
            "end_date",
            "is_active",
        ]

    def validate(self, data):
        required_fields = [
            "title",
            "menu_item",
            "offer_type",
            "discount_value",
            "start_date",
            "end_date",
        ]

        for field in required_fields:
            if not data.get(field):
                raise serializers.ValidationError(
                    {field: "This field is required"}
                )

        if data["start_date"] > data["end_date"]:
            raise serializers.ValidationError(
                "Start date cannot be after end date"
            )

        return data
    
class GodownStockSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.item_name", read_only=True)
    item_image = serializers.ImageField(source="item.item_pic", read_only=True)
    unit = serializers.CharField(source="item.unit", read_only=True)

    class Meta:
        model = GodownStock
        fields = [
            "id",
            "item",
            "item_name",
            "item_image",
            "quantity",
            "unit",
            "expiry_date",
            "updated_at",
        ]

class BranchEmployeeSerializer(serializers.ModelSerializer):
    branch_name = serializers.CharField(source='branch.branch_name', read_only=True)

    class Meta:
        model = Employees
        fields = [
            "id",
            "Eid",
            "username",
            "password",
            "role",
            "branch",
            "branch_name",
            "phone",
            "email",
            "profile_pic",
            "is_working",   # keep this for toggle
            "is_active",
            "created_at"
        ]
        extra_kwargs = {
            "password": {"write_only": True},
            "Eid": {"read_only": True},
            "created_at": {"read_only": True},
        }

    def create(self, validated_data):
        password = validated_data.pop("password")
        employee = Employees(**validated_data)
        employee.password = make_password(password)
        employee.save()
        return employee

    def update(self, instance, validated_data):
        if "password" in validated_data:
            instance.password = make_password(validated_data.pop("password"))
        return super().update(instance, validated_data)

class CartItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="menu_item.name")

    class Meta:
        model = CartItem
        fields = ["id", "name", "quantity", "price"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True)

    class Meta:
        model = Cart
        fields = ["id", "items"]


class OrderItemSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="menu_item.name")
    image = serializers.ImageField(source="menu_item.image", read_only=True)

    class Meta:
        model = OrderItem
        fields = ["name", "quantity", "price", "image"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer = CustomerSerializer(read_only=True)
    chef_name = serializers.CharField(
        source="assigned_chef.username",
        read_only=True
    )

    class Meta:
        model = Order
        fields = "__all__"

class OrderHistorySerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name")
    branch_name = serializers.CharField(source="branch.branch_name")

    class Meta:
        model = Order
        fields = [
            "id",
            "customer_name",
            "branch_name",
            "total_amount",
            "status",
            "created_at",
        ]

class ChefOrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    customer = CustomerSerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_code",
            "created_at",
            "customer",
            "items",
            "status",
            "total_amount"
        ]


