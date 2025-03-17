from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction  # ✅ 트랜잭션 적용
from .models import Inventory
from ingredients.models import Ingredient
from costcalcul.models import Recipe, RecipeItem  # ✅ 레시피 모델 추가
from .serializers import InventorySerializer
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db import transaction
from django.db.models import F
from django.utils.timezone import now

# ✅ 특정 상점의 재고 조회
class StoreInventoryView(APIView):
    
    @swagger_auto_schema(
        operation_summary="특정 상점의 재고 목록 조회",
        responses={200: "재고 목록 반환"}
    )
    
    def get(self, request, store_id):
        """ 특정 상점의 재고 목록 조회 """
        inventories = Inventory.objects.filter(ingredient__store_id=store_id)
        inventory_data = [
            {
                "ingredient_id": str(inv.ingredient.id),
                "ingredient_name": inv.ingredient.name,
                "original_stock": inv.ingredient.purchase_quantity,
                "remaining_stock": inv.remaining_stock,
                "unit": inv.ingredient.unit,
                "unit_cost": inv.ingredient.unit_cost,  # ✅ unit_cost 추가
            }
            for inv in inventories
        ]
        return Response(inventory_data, status=status.HTTP_200_OK)

 


class UseIngredientStockView(APIView):
    
    @swagger_auto_schema(
        operation_summary="특정 재료 재고 사용",
        request_body=openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={
                "used_stock": openapi.Schema(type=openapi.TYPE_NUMBER, description="사용할 재고량")
            },
            required=["used_stock"]
        ),
        responses={200: "재고 사용 성공", 400: "유효성 검사 실패"}
    )
    
    def post(self, request, store_id, ingredient_id):
        """ 특정 재료의 재고 사용 처리 """
        request_id = request.META.get('HTTP_X_REQUEST_ID', f"REQ-{now().strftime('%H%M%S%f')}")
        used_stock = request.data.get("used_stock")

        with transaction.atomic():
            inventory = get_object_or_404(Inventory, ingredient__id=ingredient_id, ingredient__store_id=store_id)
            inventory.refresh_from_db()  # ✅ 최신 상태 반영
            before_stock = inventory.remaining_stock  # 🔥 기존 재고 상태 저장

            # ✅ 사용량 검증
            if used_stock is None or not isinstance(used_stock, (int, float)) or used_stock <= 0:
                return Response({"error": "유효한 사용량(used_stock)을 입력하세요."}, status=status.HTTP_400_BAD_REQUEST)

            # 🔍 최신 original_stock 반영하여 사용 가능 재고 계산
            max_allowed_stock = inventory.ingredient.purchase_quantity  # 최신 original_stock 반영

            # ✅ 총 사용 가능 재고 계산
            total_available_stock = min(inventory.remaining_stock, max_allowed_stock)

            if total_available_stock < used_stock:
                print(f"❌ [오류] REQUEST_ID: {request_id}, 사용하려는 재고({used_stock})가 총 사용 가능 재고({total_available_stock})보다 큼")
                return Response({"error": f"최대 사용 가능한 재고는 {total_available_stock}입니다."}, status=status.HTTP_400_BAD_REQUEST)

            # ✅ 재고 차감 로직
            Inventory.objects.filter(id=inventory.id).update(remaining_stock=F('remaining_stock') - used_stock)
            inventory.refresh_from_db()  # ✅ 최신 상태 반영
            after_stock = inventory.remaining_stock

            print(f"✅ [재고 차감 완료] REQUEST_ID: {request_id}, 차감 전: {before_stock}, 차감할 수량: {used_stock}, 차감 후: {after_stock}")

        return Response(
            {
                "ingredient_id": inventory.ingredient.id,
                "ingredient_name": inventory.ingredient.name,
                "original_stock": inventory.ingredient.purchase_quantity,  
                "remaining_stock": inventory.remaining_stock,
                "unit": inventory.ingredient.unit,
            },
            status=status.HTTP_200_OK,
        )



# ✅ 레시피 삭제 시 재료 재고 복구
class DeleteRecipeView(APIView):
    
    @swagger_auto_schema(
        operation_summary="레시피 삭제 및 재료 재고 복구",
        responses={204: "레시피 삭제 및 재고 복구 완료", 404: "레시피를 찾을 수 없음"}
    )    
    def delete(self, request, store_id, recipe_id):
        """ 레시피 삭제 시 사용한 재료를 다시 재고로 복구 """
        recipe = get_object_or_404(Recipe, id=recipe_id, store_id=store_id)
        recipe_items = RecipeItem.objects.filter(recipe=recipe)

        with transaction.atomic():  # ✅ 트랜잭션 적용
            for item in recipe_items:
                inventory_item = Inventory.objects.filter(ingredient=item.ingredient).first()
                if inventory_item:
                    max_stock = inventory_item.ingredient.purchase_quantity  # ✅ 최신 original_stock
                    new_remaining_stock = inventory_item.remaining_stock + item.quantity_used

                    # 🔥 만약 original_stock보다 남은 재고가 더 크다면 조정
                    if new_remaining_stock > max_stock:
                        new_remaining_stock = max_stock

                    inventory_item.remaining_stock = new_remaining_stock
                    inventory_item.save()

            # ✅ 레시피 및 연결된 RecipeItem 삭제
            recipe_items.delete()
            recipe.delete()

        return Response({"message": "레시피 삭제 및 재고 복구 완료"}, status=status.HTTP_204_NO_CONTENT)


