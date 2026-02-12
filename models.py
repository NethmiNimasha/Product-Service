from sqlalchemy import Boolean, Column, Integer, String, Text
from database import Base

class Product(Base):
    __tablename__ = "products"

    product_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)
    price = Column(String(20), nullable=False)
   
   
class Order_Product(Base):
    __tablename__ = "order_products"

    order_product_id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, nullable=False)
    product_id = Column(Integer, nullable=False)
    quantity = Column(Integer, nullable=False)

class Proof_Of_Delivery(Base):
    __tablename__ = "proof_of_delivery"

    pod_id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, nullable=False)
    package_id = Column(Integer, nullable=False)
    photo = Column(String(255), nullable=True)
    delivery_time = Column(String(255), nullable=True)
 