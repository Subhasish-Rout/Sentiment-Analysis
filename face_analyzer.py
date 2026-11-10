import cv2
from deepface import DeepFace

cap = cv2.VideoCapture(0)

while True:
    ret, frame = cap.read()
    if not ret:
        break

    try:
        result = DeepFace.analyze(
            frame,
            actions=["age", "gender", "emotion"],
            enforce_detection=False
        )

        age = result[0]["age"]
        gender = result[0]["dominant_gender"]
        emotion = result[0]["dominant_emotion"]

        label = f"{gender} | Age: {age} | {emotion}"

        cv2.putText(frame, label, (50, 50),
                   cv2.FONT_HERSHEY_SIMPLEX, 1,
                   (0, 255, 0), 2)

    except:
        pass

    cv2.imshow("Face Analyzer", frame)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()