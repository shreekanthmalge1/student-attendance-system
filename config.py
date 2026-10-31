import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
SECRET_KEY = os.getenv("SECRET_KEY")

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)

db = client["student_attendance"]

students = db["students"]
teachers = db["teachers"]
users = db["users"]
subjects = db["subjects"]
attendance = db["attendance"]