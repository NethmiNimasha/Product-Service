from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Annotated

import models
from database import SessionLocal, engine

app = FastAPI(title = "Product Service, Proof of Delivery Service")
UPLOAD_DIR = Path(__file__).resolve().parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


def _ensure_products_schema() -> None:
    """Ensure DB schema matches current models (no full migrations required)."""
    try:
        models.Base.metadata.create_all(bind=engine)
    except Exception:
    
        pass

    try:
        with engine.begin() as conn:
           
            discounts_count = conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'products'
                    
                    """
                )
            ).scalar_one()
            if int(discounts_count) == 0:
                conn.execute(text("ALTER TABLE products ADD COLUMN discounts VARCHAR(10) NULL"))

        
            price_type = conn.execute(
                text(
                    """
                    SELECT DATA_TYPE
                    FROM INFORMATION_SCHEMA.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'products'
                      AND COLUMN_NAME = 'price'
                    """
                )
            ).scalar_one_or_none()
            if price_type is not None and str(price_type).lower() not in {"varchar", "text", "char"}:
                conn.execute(text("ALTER TABLE products MODIFY COLUMN price VARCHAR(20) NOT NULL"))
    except Exception:
      
        pass


_ensure_products_schema()


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    message = exc.detail if isinstance(exc.detail, str) else "Request error"
    return JSONResponse(status_code=exc.status_code, content={"message": message})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"message": "Bad request"})


@app.exception_handler(IntegrityError)
async def integrity_exception_handler(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=400, content={"message": "Duplicate product (id or name)"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"message": "Internal server error"})


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


db_dependency = Annotated[Session, Depends(get_db)]


def _normalize_price(value: str) -> str:
    """Accepts prices like '123', '123.0', '123.00' and returns 2dp string."""
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise HTTPException(status_code=400, detail="Bad request")
    return f"{dec:.2f}"


def _product_to_dict(product: models.Product) -> dict:
    return {
        "id": product.product_id,
        "name": product.name,
        "price": str(product.price),
       
    }


class ProductIn(BaseModel):
    
    name: str
    price: str
  

    class Config:
        populate_by_name = True


   

class ProductPut(BaseModel):
    name: str
    price: str




@app.get("/", status_code=status.HTTP_200_OK)
async def get_all_products(db: db_dependency):
    products = db.query(models.Product).all()
    return [_product_to_dict(p) for p in products]


@app.get("/{id}", status_code=status.HTTP_200_OK)
async def get_product_by_id(id: int, db: db_dependency):
    product = db.query(models.Product).filter(models.Product.product_id == id).first()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return _product_to_dict(product)


@app.post("/new", status_code=status.HTTP_201_CREATED)
async def create_new_product(product: ProductIn, db: db_dependency):
    db_product = models.Product(
       
        name=product.name,
        price=_normalize_price(product.price),
        
    )
    db.add(db_product)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    return {"message": "Product created successfully"}





@app.put("/{id}", status_code=status.HTTP_200_OK)
async def put_product(id: int, product: ProductPut, db: db_dependency):
    db_product = db.query(models.Product).filter(models.Product.product_id == id).first()
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    db_product.name = product.name
    db_product.price = _normalize_price(product.price)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise

    return {"message": "Product updated successfully"}


@app.delete("/{id}", status_code=status.HTTP_200_OK)
async def delete_product(id: int, db: db_dependency):
    db_product = db.query(models.Product).filter(models.Product.product_id == id).first()
    if db_product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    db.delete(db_product)
    db.commit()
    return {"message": "Product deleted successfully"}




# --- Proof of Delivery ---

def _pod_to_dict(pod: models.Proof_Of_Delivery) -> dict:
    return {
        "pod_id": pod.pod_id,
        "order_id": pod.order_id,
        "package_id": pod.package_id,
        
        "photo": pod.photo,
        "delivery_time": pod.delivery_time,
    }


class ProofOfDeliveryCreate(BaseModel):
    pod_id: int
    order_id: int
    package_id: int
   
    photo: str | None = None
    delivery_time: str


class ProofOfDeliveryPut(BaseModel):
    order_id: int
    package_id: int
   
    photo: str | None = None
    delivery_time: str





@app.post("/proof_of_delivery", status_code=status.HTTP_201_CREATED)
async def create_proof_of_delivery(
    db: db_dependency,
    pod_id: int,
    order_id: int = Form(...),
    package_id: int = Form(...),
   
    delivery_time: str = Form(...),
    photo: UploadFile | None = File(None),
):
    photo_url: str | None = None
    if photo is not None:
        file_suffix = Path(photo.filename or "").suffix.lower()
        allowed = {".jpg", ".jpeg", ".png", ".webp"}
        if file_suffix not in allowed:
            raise HTTPException(status_code=400, detail="Bad request")

        file_name = f"pod_{uuid4().hex}{file_suffix}"
        dest_path = UPLOAD_DIR / file_name
        dest_path.write_bytes(await photo.read())
        photo_url = f"/uploads/{file_name}"

    db_pod = models.Proof_Of_Delivery(
        order_id=order_id,
        package_id=package_id,
     
        photo=photo_url,
        delivery_time=delivery_time,
    )
    db.add(db_pod)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    return {"message": "Proof of delivery created successfully"}



@app.get("/proof_of_delivery/{pod_id}", status_code=status.HTTP_200_OK)
async def read_proof_of_delivery_by_id(pod_id: int, db: db_dependency):
    pod = db.query(models.Proof_Of_Delivery).filter(models.Proof_Of_Delivery.pod_id == pod_id).first()
    if pod is None:
        raise HTTPException(status_code=404, detail="Proof of delivery not found")
    return _pod_to_dict(pod)


@app.put("/proof_of_delivery/{pod_id}", status_code=status.HTTP_200_OK)
async def put_proof_of_delivery(
    pod_id: int,
    db: db_dependency,
    order_id: int = Form(...),
    package_id: int = Form(...),
    
    delivery_time: str = Form(...),
    photo: UploadFile | None = File(None),
):
    db_pod = db.query(models.Proof_Of_Delivery).filter(models.Proof_Of_Delivery.pod_id == pod_id).first()
    if db_pod is None:
        raise HTTPException(status_code=404, detail="Proof of delivery not found")

    photo_url: str | None = None
    if photo is not None:
        file_suffix = Path(photo.filename or "").suffix.lower()
        allowed = {".jpg", ".jpeg", ".png", ".webp"}
        if file_suffix not in allowed:
            raise HTTPException(status_code=400, detail="Bad request")

        file_name = f"pod_{pod_id}_{uuid4().hex}{file_suffix}"
        dest_path = UPLOAD_DIR / file_name
        dest_path.write_bytes(await photo.read())
        photo_url = f"/uploads/{file_name}"

    db_pod.order_id = order_id
    db_pod.package_id = package_id
   
    db_pod.delivery_time = delivery_time
    if photo_url is not None:
        db_pod.photo = photo_url

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise

    return {"message": "Proof of delivery updated successfully"}







@app.delete("/proof_of_delivery/{pod_id}", status_code=status.HTTP_200_OK)
async def delete_proof_of_delivery(pod_id: int, db: db_dependency):
    db_pod = db.query(models.Proof_Of_Delivery).filter(models.Proof_Of_Delivery.pod_id == pod_id).first()
    if db_pod is None:
        raise HTTPException(status_code=404, detail="Proof of delivery not found")
    db.delete(db_pod)
    db.commit()
    return {"message": "Proof of delivery deleted successfully"}


