from flask import Flask, jsonify, request
import threading
import time
import uuid
import cv2
from minio import Minio
from paho.mqtt import client as mqtt_client
import os
from flask_cors import CORS,cross_origin
from collections import defaultdict

os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "timeout;5000"  # 5 giây
app = Flask(__name__)
CORS(app)

camera_list = {
    "cam1": {"name": "Webcam", "rtsp": "0"},
    "cam2": {"name": "H2 304 low", "rtsp": "rtsp://admin:Admin123@117.4.240.104:8082/Streaming/Channels/102"},
    "cam3": {"name": "H2 304 high", "rtsp": "rtsp://admin:Admin123@117.4.240.104:8082/Streaming/Channels/101"},
    "cam4": {"name": "Flycam Hà Giang", "rtsp": "../videos/flycam.mp4"},
}
FPS = 15
MINIO_ENDPOINT = "172.20.10.5:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
MINIO_BUCKET = "camera-images"

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key=MINIO_ACCESS_KEY,
    secret_key=MINIO_SECRET_KEY,
    secure=False
)
print("✅ MinIO client initialized")

if not minio_client.bucket_exists(MINIO_BUCKET):
    minio_client.make_bucket(MINIO_BUCKET)
    print(f"✅ Tạo bucket {MINIO_BUCKET}")
else:
    print(f"✅ Bucket {MINIO_BUCKET} đã tồn tại")

MQTT_BROKER = "172.20.10.5"
MQTT_PORT = 1883
mqtt_pub = mqtt_client.Client(client_id="flaskapi-pub", protocol=mqtt_client.MQTTv311)
mqtt_pub.connect(MQTT_BROKER, MQTT_PORT)

client_registry = {}  # {client_id: {"type": ..., "start": ..., "topics": [...]}}

def stream_worker(cam_id):
    rtsp_url = camera_list[cam_id]["rtsp"]
    if rtsp_url == "0":
        cap = cv2.VideoCapture(0)
    else:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    print(f"🎥 Bắt đầu stream camera: {cam_id}")

    while True:
        try:
            ret, frame = cap.read()
            if not ret:
                print(f"[{cam_id}] ❌ Không đọc được frame.")
                time.sleep(1)
                continue

            filename = f"{cam_id}_{uuid.uuid4()}.jpg"
            local_path = f"/tmp/{filename}"
            cv2.imwrite(local_path, frame)

            try:
                minio_client.fput_object(
                    MINIO_BUCKET,
                    filename,
                    local_path,
                    content_type="image/jpeg"
                )
                image_url = f"http://172.20.10.5:9000/{MINIO_BUCKET}/{filename}"
                mqtt_pub.publish(f"camera/{cam_id}", image_url)
                print(f"[{cam_id}] ✅ Gửi ảnh: {image_url}")
            except Exception as e:
                print(f"[{cam_id}] ⚠️ Lỗi upload/MQTT: {e}")

            time.sleep(1/FPS)
        except Exception as e:
            print(f"[{cam_id}] ⚠️ Lỗi camera: {e}")

@app.route("/cameras")
def get_cameras():
    print("✅ Lấy danh sách camera")
    return jsonify(camera_list)

@app.route("/register", methods=["POST", "OPTIONS"])
@cross_origin(origins="*")
def register_client():
    data = request.get_json(force=True)  # đảm bảo parse JSON đúng
    print("📥 Nhận dữ liệu register:", data)

    client_id = data.get("client_id")
    client_type = data.get("type")
    topics = data.get("topics", [])

    if not client_id or not client_type:
        return jsonify({"error": "client_id and type are required"}), 400

    client_registry[client_id] = {"type": client_type, "topics": topics}
    if client_type == "subscriber":
        for topic in topics:
            topic_subscriptions[topic].add(client_id)

    return jsonify({"status": "ok", "client_id": client_id})

@app.route("/topics")
def get_topics():
    return jsonify(list(topic_subscriptions.keys()))

@app.route("/admin/status", methods=["GET"])
def get_status():
    return jsonify({
        "clients": client_registry,
    })


if __name__ == "__main__":
    print("🚀 Starting static Flask camera server...")
    for cam_id in camera_list.keys():
        threading.Thread(target=stream_worker, args=(cam_id,), daemon=True).start()

    app.run(host="0.0.0.0", port=5005, debug=True)