# MQTT_cam_manager
Multiple streaming cameras using MQTT

Publisher:
- Cameras
- Save to Minio

client_registry: lưu thông tin các client đã kết nối đến 
    type: dict
    example: {"sub-123": {"type": "subscriber", "start": start_time, "topics": ["camera/cam1"]}}


Client
- on connect -> client of MQTT -> POST /register
- sub/unsub -> update client_registry with topics using POST /register