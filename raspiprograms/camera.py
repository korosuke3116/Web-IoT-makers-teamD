from flask import Flask, request, jsonify, send_file
from picamera2 import Picamera2
import schedule
import os
import threading
import time
from datetime import datetime
import requests

app = Flask(__name__)

# Picamera2の初期化
camera = Picamera2()
camera.configure(camera.create_still_configuration())

# 出力ディレクトリ
output_dir = "processed_images"
os.makedirs(output_dir, exist_ok=True)

# Colab上のYOLOサーバーのURL
COLAB_SERVER_URL = "http://172.28.0.12:5000/upload"

# YOLOで画像を処理する関数
def process_image_with_yolo(tag="manual"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    input_path = f"{output_dir}/input_{tag}_{timestamp}.jpg"
    output_path = f"{output_dir}/output_{tag}_{timestamp}.jpg"

    try:
        # カメラで画像をキャプチャ
        camera.start()
        camera.capture_file(input_path)
        camera.stop()
        print(f"Captured image: {input_path}")

        # Colabサーバーに画像を送信
        with open(input_path, "rb") as image_file:
            files = {"file": image_file}
            response = requests.post(COLAB_SERVER_URL, files=files)

        # Colabサーバーから加工済み画像とクラス名を取得
        if response.status_code == 200:
            result = response.json()
            yolo_output_url = result.get("output_url")
            detected_classes = result.get("classes", [])

            # YOLOの出力画像をローカルに保存
            if yolo_output_url:
                yolo_image = requests.get(yolo_output_url)
                with open(output_path, "wb") as f:
                    f.write(yolo_image.content)
                print(f"Processed image saved: {output_path}")
                return {"output_path": output_path, "classes": detected_classes}
            else:
                print("YOLO processing failed: No output URL")
        else:
            print(f"Error from Colab server: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"Error processing image: {e}")

    return None

# スケジュール設定
def schedule_tasks():
    schedule.every().day.at("06:00").do(process_image_with_yolo, tag="morning")
    schedule.every().day.at("12:00").do(process_image_with_yolo, tag="noon")
    schedule.every().day.at("18:00").do(process_image_with_yolo, tag="evening")

# スケジュールのスレッド
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

# ボタン押下時の画像処理
@app.route("/process", methods=["POST"])
def process():
    result = process_image_with_yolo(tag="manual")  # 画像取得と加工

    if result:
        output_path = result["output_path"]
        detected_classes = result["classes"]

        return jsonify({
            "image_url": f"/images/{os.path.basename(output_path)}",
            "classes": detected_classes,
        })
    else:
        return jsonify({"error": "Image processing failed"}), 500

# 加工画像を提供
@app.route("/images/<filename>")
def images(filename):
    return send_file(f"{output_dir}/{filename}", mimetype="image/jpeg")

# メインスクリプト
if __name__ == "__main__":
    # スケジュールの設定を開始
    schedule_tasks()
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # Flaskサーバーを開始
    app.run(host="0.0.0.0", port=5000)
