from rest_framework import serializers
from .models import Recipe, RecipeItem
from inventory.models import Inventory
from ingredients.models import Ingredient  
from django.shortcuts import get_object_or_404
from decimal import Decimal
from .utils import calculate_recipe_cost
import logging
from django.db import transaction
from rest_framework import serializers
from .recipe_item_serializers import RecipeItemSerializer



logger = logging.getLogger(__name__)

#  레시피(Recipe) 시리얼라이저
class RecipeSerializer(serializers.ModelSerializer):
    recipe_name = serializers.CharField(source="name", allow_blank=False)  #  필수 값 
    recipe_cost = serializers.DecimalField(source="sales_price_per_item", max_digits=10, decimal_places=2, required=False)  # ✅ 선택 값
    recipe_img = serializers.ImageField(required=False, allow_null=True)  #  선택 값
    ingredients = RecipeItemSerializer(many=True, required=False)  # 재료
    production_quantity = serializers.IntegerField(source="production_quantity_per_batch", required=False)  #  선택 값
    total_ingredient_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True) # 총 재료가격
    production_cost = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)


    class Meta:
        model = Recipe
        fields = [
                'id', 'recipe_name', 'recipe_cost', 'recipe_img', 
                'is_favorites', 'ingredients', 'production_quantity', 
                'total_ingredient_cost', 'production_cost'
        ]
        read_only_fields = ['id']
        
    def get_ingredients(self, obj):
        from .serializers import RecipeItemSerializer  # 지연 임포트
        recipe_items = RecipeItem.objects.filter(recipe=obj)
        return RecipeItemSerializer(recipe_items, many=True).data    

    def validate(self, data):
        """🚀 빈 값이면 DB에서 기존 값 가져오기"""
        instance = self.instance  #  기존 Recipe 객체 (PUT 요청 시)

        if instance:
            data.setdefault("sales_price_per_item", instance.sales_price_per_item)  # 기존 값 유지
            data.setdefault("production_quantity_per_batch", instance.production_quantity_per_batch)  # 기존 값 유지
            data.setdefault("recipe_img", instance.recipe_img)
        return data
        
        # put 요청시
    def update(self, instance, validated_data):
        instance.name = validated_data.get("name", instance.name)
        instance.sales_price_per_item = validated_data.get("sales_price_per_item", instance.sales_price_per_item)
        instance.production_quantity_per_batch = validated_data.get("production_quantity_per_batch", instance.production_quantity_per_batch)

        if "recipe_img" in validated_data:
            instance.recipe_img = validated_data["recipe_img"]
            # print(f" 이미지 저장됨: {instance.recipe_img}")

        #  재료 구매량 변경 시, 기존 값 백업 (프론트에서 purchase_quantity 없이도 작동)
        ingredients_data = validated_data.get("ingredients", [])
        for ing in ingredients_data:
            ingredient_id = ing.get("ingredient_id")
            required_amount = Decimal(str(ing.get("required_amount", 0)))

            if ingredient_id:
                ingredient = get_object_or_404(Ingredient, id=ingredient_id)

                # DB에서 최신 값을 불러와 비교
                latest_ingredient = Ingredient.objects.get(id=ingredient_id)
                old_qty = latest_ingredient.original_stock_before_edit
                current_qty = latest_ingredient.purchase_quantity

                if old_qty and current_qty < old_qty:
                    # print("original_stock 감소 감지, used_stock 초기화 적용")
                    required_amount = Decimal("0.0")

                # required_amount 반영
                ing["required_amount"] = float(required_amount)

        instance.save()
        return instance

        
    def create(self, validated_data):
        ingredients_data = validated_data.pop('ingredients', [])  
        # print(f" [validated_data]: {validated_data}")
        # print(f" [ingredients_data]: {ingredients_data}")
        recipe = Recipe.objects.create(**validated_data)

        # print(f" [레시피 생성] 이름: {recipe.name}, 총 재료 수: {len(ingredients_data)}")

        ingredient_costs = []

        for idx, ingredient_data in enumerate(ingredients_data, 1):
            # print(f"\n [#{idx}] ingredient_data:", ingredient_data)

            try:
                ingredient = get_object_or_404(Ingredient, id=ingredient_data["ingredient_id"])
                # print(f" Ingredient 조회 성공: {ingredient.name}")
            except:
                # print(f" Ingredient 조회 실패: ID = {ingredient_data.get('ingredient_id')}")
                continue

            required_amount = Decimal(str(ingredient_data.get("quantity_used", 0)))
            unit = ingredient_data.get("unit", ingredient.unit)

            inventory, created = Inventory.objects.get_or_create(
                ingredient=ingredient,
                defaults={"remaining_stock": ingredient.purchase_quantity}
            )

            RecipeItem.objects.create(
                recipe=recipe,
                ingredient=ingredient,
                quantity_used=required_amount,
                unit=unit
            )
            # print(f" RecipeItem 생성 완료: {ingredient.name}, 사용량: {required_amount}, 단위: {unit}")

            ingredient_costs.append({
                "ingredient_id": str(ingredient.id),
                "ingredient_name": ingredient.name,
                "unit_price": ingredient.unit_cost,  
                "quantity_used": required_amount,
                "unit": unit
            })

        #  원가 계산 후 DB에 저장
        cost_data = calculate_recipe_cost(
            ingredients=ingredient_costs,
            sales_price_per_item=recipe.sales_price_per_item,  
            production_quantity_per_batch=recipe.production_quantity_per_batch  
        )


        recipe.total_ingredient_cost = Decimal(str(cost_data["total_material_cost"]))
        recipe.production_cost = Decimal(str(cost_data["cost_per_item"]))

        with transaction.atomic():
            Recipe.objects.filter(id=recipe.id).update(
                total_ingredient_cost=recipe.total_ingredient_cost,
                production_cost=recipe.production_cost
            )

        updated_recipe = Recipe.objects.get(id=recipe.id)

        return updated_recipe  # 시리얼라이저에 반영

    def get_total_ingredient_cost(self, obj):
        """ 응답에 `total_ingredient_cost` 추가 (None 방지)"""
        return getattr(obj, "total_ingredient_cost", 0)

    def get_production_cost(self, obj):
        """ 응답에 `production_cost` 추가 (None 방지)"""
        return getattr(obj, "production_cost", 0)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["recipe_cost"] = data["recipe_cost"] if data["recipe_cost"] is not None else 0

        recipe_items = RecipeItem.objects.filter(recipe=instance)
        # print(f" [to_representation] 연결된 RecipeItem 개수: {recipe_items.count()}")
        for item in recipe_items:
            print(f" {item.ingredient.name} - {item.quantity_used}")

        data["ingredients"] = [
            {
                "ingredient_id": str(item.ingredient.id),
                "required_amount": item.quantity_used
            }
            for item in recipe_items
        ]

        return data
