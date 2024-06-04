from flask import Flask, jsonify, send_file, request
from pyngrok import ngrok,conf
import requests
import pandas as pd
import matplotlib.pyplot as plt
from pymongo import MongoClient
import matplotlib.font_manager as fm
from bson.objectid import ObjectId
import numpy as np
import tensorflow as tf
import datetime
import time
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
import matplotlib.patches as mpatches
import librosa
import librosa.display
from threading import Thread
import io

#전역변수 선언부
app = Flask(__name__)
connection_string = 'mongodb+srv://hansunguniv001:hansung@cluster0.hlw86l4.mongodb.net/'

# MongoDB 클라이언트 설정
client = MongoClient(connection_string, tls=True, tlsAllowInvalidCertificates=True)
db = client['test']  # 데이터베이스 이름
# coeffie_control 컬렉션 선언
control_collection = db['coeffie_control']
# coeffie_record 컬렉션 선언
record_collection = db['coeffie_record']
control_mfcc_avg = db['control_mfcc_avg']
record_mfcc_avg = db['record_mfcc_avg']

#모델 훈련 관련
batch_size = 64
pca = PCA(n_components=2)

# 한글 폰트 경로 설정
font_path = r'C:\Windows\Fonts\H2GTRE.TTF'  # Windows의 윤고딕 폰트 파일 불러옴
# 폰트 속성 설정
font_prop = fm.FontProperties(fname=font_path, size=12)
plt.rc('font', family=font_prop.get_name())

# 모델 구성
model = tf.keras.Sequential([
    tf.keras.layers.Dense(64, activation='relu', input_shape=(12,)),  # 입력 형태는 12개의 특징을 가진 벡터
    tf.keras.layers.BatchNormalization(),
    tf.keras.layers.LeakyReLU(alpha=0.01),
    tf.keras.layers.Dense(32, activation='tanh'),
    # tf.keras.layers.Dense(64, activation='relu'),
    tf.keras.layers.Dropout(0.4),
    tf.keras.layers.Dense(16, activation='relu', kernel_regularizer=tf.keras.regularizers.l2(0.001)),
    tf.keras.layers.Dense(1, activation='sigmoid')
])

# 필요한 데이터 전역변수
mfcc_record_train_values = None
mfcc_record_test_values = None
mfcc_control_train_values = None
mfcc_control_test_values = None
combined_labels = None
control_predicted_labels = None
record_predicted_labels = None
combined_mfcc = None
files_control_id = None
files_record_id = None
mfcc_control_data = None
mfcc_record_data = None

@app.route('/plot_spectrum', methods=['POST'])
def plot_spectrum():
    data = request.json
    x = data['x']
    y = data['y']
    frame_index = data['frame_index']
    file_index = data['file_index']

    plt.figure(figsize=(10, 6))
    plt.plot(x, y)
    plt.xlabel('Frequency Bin')
    plt.ylabel('Magnitude')
    plt.title(f'FFT Spectrum for File {file_index}, Frame {frame_index}')

    image_path = f'images/fft_spectrum_file{file_index}_frame{frame_index}.png'
    plt.savefig(image_path)
    plt.close()

    # Node.js 서버로 이미지 전송
    with open(image_path, 'rb') as f:
        response = requests.post('http://localhost:3000/upload_image', files={'image': f})
        print(response.text)

    return jsonify({'message': 'Plot saved and uploaded to Node.js server', 'image_path': image_path})

@app.route('/')
def start():
    return "Hello ngrok!"


@app.route('/import_dataset', methods=['GET'])
def import_dataset():
    global mfcc_control_test_values, mfcc_control_train_values, mfcc_record_test_values, mfcc_record_train_values, mfcc_control_data, mfcc_record_data, files_control_id, files_record_id
    # 가장 최근 데이터 하나만 조회
    latest_coef_control = control_collection.find_one(sort=[('_id', -1)])
    # 'files_control_id' 필드의 값을 변수에 저장
    files_control_id = latest_coef_control['files_control_id'] if latest_coef_control and 'files_control_id' in latest_coef_control else None
    print(files_control_id)  # id 테스트 출력
    control_cursor = control_collection.find({'files_control_id': files_control_id})  # id에 해당하는 레코드들만 가져옴
    # Cursor에서 데이터를 리스트로 변환 후 DataFrame 생성
    mfcc_control_data = pd.DataFrame(list(control_cursor))

    # 가장 최근 레코드 가져오기
    latest_coef_record = record_collection.find_one(sort=[('_id', -1)])
    # 'files_record_id' 필드의 값을 변수에 저장
    files_record_id = latest_coef_record['files_record_id'] if latest_coef_record and 'files_record_id' in latest_coef_record else None
    print(files_record_id)  # id 테스트 출력
    record_cursor = record_collection.find({'files_record_id': files_record_id})  # id에 해당하는 레코드들만 가져옴
    # Cursor에서 데이터를 리스트로 변환 후 DataFrame 생성
    mfcc_record_data = pd.DataFrame(list(record_cursor))

    # 필요한 열만 선택 (예: MFCC1부터 MFCC12까지)
    mfcc_control_data = mfcc_control_data.loc[:, 'MFCC1':'MFCC12']
    mfcc_record_data = mfcc_record_data.loc[:, 'MFCC1':'MFCC12']

    # DataFrame에서 numpy 배열로 변환
    mfcc_record_values = mfcc_record_data.to_numpy()
    mfcc_control_values = mfcc_control_data.to_numpy()

    # 표준화
    scaler = StandardScaler()
    normalized_record_values = scaler.fit_transform(mfcc_record_values)
    normalized_control_values = scaler.transform(mfcc_control_values)

    # 데이터를 8:2 비율로 train과 test로 분리
    mfcc_record_train_values, mfcc_record_test_values = train_test_split(normalized_record_values, test_size=0.2,
                                                                         random_state=42)
    mfcc_control_train_values, mfcc_control_test_values = train_test_split(normalized_control_values, test_size=0.2,
                                                                           random_state=42)
    return "import label completed!"

@app.route('/label_setting', methods=['GET'])
def labeling():
    #전역 변수 선언
    global combined_labels, combined_mfcc, mfcc_control_train_values, mfcc_record_train_values

    # control_mfcc와 record_mfcc를 합친 데이터셋 생성
    combined_mfcc = np.concatenate((mfcc_control_train_values, mfcc_record_train_values), axis=0)

    # 클러스터링을 위한 KMeans 모델 생성
    kmeans = KMeans(n_clusters=2, n_init = 12)

    # combined_mfcc에 대해 클러스터링 수행
    kmeans.fit(combined_mfcc)

    # 클러스터링 결과를 레이블로 사용
    combined_labels = kmeans.labels_

    # PCA를 사용해 데이터를 2차원으로 축소
    reduced_data = pca.fit_transform(combined_mfcc)

    # 레이블에 따라 색상을 지정
    colors = ['purple' if label == 0 else 'darkorange' for label in combined_labels]

    # 그래프 생성
    fig, ax = plt.subplots()
    ax.scatter(reduced_data[:, 0], reduced_data[:, 1], c=colors)

    # 클러스터 중심을 플롯
    centers = pca.transform(kmeans.cluster_centers_)
    ax.scatter(centers[:, 0], centers[:, 1], c='black', s=200, alpha=0.5)

    # 범례 추가
    purple_patch = mpatches.Patch(color='purple', label='Label 0')
    yellow_patch = mpatches.Patch(color='darkorange', label='Label 1')
    ax.legend(handles=[purple_patch, yellow_patch])

    ax.set_title('녹취 파일 & 실시간 파일 클러스트링 결과 그래프')

    # 이미지를 메모리에 저장
    img = io.BytesIO()
    fig.savefig(img, format='png')
    img.seek(0)

    # 이미지 파일로 저장
    with open(f'images/clustering_label_{files_control_id}.png', 'wb') as f:
        f.write(img.getbuffer())

    #Node.js 서버로 이미지 전송
    # with open(f'images/clustering_label_{files_control_id}.png', 'rb') as f:
    #     response = requests.post('http://localhost:3000/upload_image', files={'image': f})  # Node.js 서버 포트는 3000입니다.
    #     print(response.text)

    return "clustering_label.png processed and sent to Node.js server"

@app.route('/training', methods=['GET'])
def training():
    global combined_labels, combined_mfcc

    if combined_labels is None:
        return jsonify({"error": "Labels not set. Please run /label_setting first."}), 400

    # 데이터 분리 없이 전체 데이터를 사용
    train_data = combined_mfcc
    train_labels = combined_labels

    # TensorFlow 데이터셋 생성
    train_dataset = tf.data.Dataset.from_tensor_slices((train_data, train_labels)).batch(batch_size)


    # 모델 컴파일
    model.compile(optimizer='rmsprop',
                    loss='binary_crossentropy',
                    metrics=['accuracy'])

    # 모델 컴파일 및 학습
    history = model.fit(train_dataset, epochs=10)

    # 두 번째 그래프 생성 (학습 손실과 정확도)
    fig, ax = plt.subplots(1, 2, figsize=(20, 6))  # 가로로 길고 세로로 짧게 설정

    # 학습 손실 값
    ax[0].plot(history.history['loss'], label='실제 값과 모델의 예측값 간의 오차율')
    ax[0].set_xlabel('훈련 횟수')
    ax[0].set_ylabel('오차율')
    ax[0].set_title('훈련 횟수에 따른 모델의 오차율')
    ax[0].legend()

    # 학습 정확도 값
    ax[1].plot(history.history['accuracy'], label='모델의 정확도', color='red')
    ax[1].set_xlabel('훈련 횟수')
    ax[1].set_ylabel('정확도')  # 수정: 정확도에 맞는 y축 레이블
    ax[1].set_title('훈련 횟수에 따른 모델의 정확도')
    ax[1].legend()

    fig.tight_layout()

    # 이미지를 메모리에 저장
    img = io.BytesIO()
    fig.savefig(img, format='png')
    img.seek(0)

    # 이미지 파일로 저장
    with open(f'images/train_acc_loss_{files_control_id}.png', 'wb') as f:
        f.write(img.getbuffer())

    # # Node.js 서버로 이미지 전송
    # with open(f'images/train_acc_loss_{files_control_id}.png', 'rb') as f:
    #     response = requests.post('http://localhost:3000/upload_image', files={'image': f})
    #     print(response.text)

    return "Training Image processed and sent to Node.js server"

@app.route('/mfcc_spectrum', methods=['GET'])
def mfcc_spectrum():
    global mfcc_control_data, mfcc_record_data
    def safe_float_convert(value):
        try:
            return float(value)
        except ValueError:
            return np.nan

    # CSV 파일에서 오디오 데이터 추출 및 정규화
    def process_and_normalize_mfccs(data):
        mfcc_data = data.iloc[1:, 2:14].applymap(safe_float_convert).to_numpy()
        # 각 계수별로 정규화
        mfcc_data -= mfcc_data.min(axis=0)  # 최소값을 0으로 조정
        mfcc_data /= mfcc_data.max(axis=0)  # 최대값으로 나누어 0과 1 사이로 조정
        return mfcc_data.flatten()

    audio_data1 = process_and_normalize_mfccs(mfcc_record_data)
    audio_data2 = process_and_normalize_mfccs(mfcc_control_data)

    sr = 22050  # 샘플 레이트

    # 데이터 정규화를 위한 수정된 함수
    def normalize_positive_mfcc(mfcc_data):
        mfcc_data = np.maximum(mfcc_data, 0)  # 음수 값 제거
        mfcc_data /= np.max(mfcc_data)  # 최대값으로 나누어 스케일링
        return mfcc_data

    # MFCC 계산
    mfccs1 = librosa.feature.mfcc(y=audio_data1, sr=sr, n_mfcc=13)
    mfccs2 = librosa.feature.mfcc(y=audio_data2, sr=sr, n_mfcc=13)

    # 정규화 수행
    mfccs1 = normalize_positive_mfcc(mfccs1)
    mfccs2 = normalize_positive_mfcc(mfccs2)

    # 시각화
    fig, axes = plt.subplots(nrows=1, ncols=2, figsize=(14, 6))
    img1 = librosa.display.specshow(mfccs1, sr=sr, x_axis='time', ax=axes[0], cmap='coolwarm')
    axes[0].set_title('증거물 녹취 파일 MFCC Spectrum')
    axes[0].set_xlabel('Time')
    axes[0].set_ylabel('MFCC Coefficients')
    fig.colorbar(img1, ax=axes[0])

    img2 = librosa.display.specshow(mfccs2, sr=sr, x_axis='time', ax=axes[1], cmap='coolwarm')
    axes[1].set_title('실시간 파일 MFCC Spectrum')
    axes[1].set_xlabel('Time')
    axes[1].set_ylabel('MFCC Coefficients')
    fig.colorbar(img2, ax=axes[1])

    # 전체 그림에 대한 서브 타이틀 설정
    fig.suptitle('위 그래프는 MFCC 계수값들을 정규화하여 최소 0, 최대 1의 실수값들의 분포를 표현한 것입니다', fontsize=12)
    # Layout 조정 전에 서브 타이틀이 그래프에 영향을 주지 않도록 조정
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])  # rect는 [left, bottom, right, top] 형태로 조정
    plt.tight_layout()

    # 이미지를 메모리에 저장
    img = io.BytesIO()
    fig.savefig(img, format='png')
    img.seek(0)

    # 이미지 파일로 저장
    with open(f'images/mfcc_spectrum_graph_{files_control_id}.png', 'wb') as f:
        f.write(img.getbuffer())

    # Node.js 서버로 이미지 전송
    # with open(f'images/mfcc_spectrum_graph_{files_control_id}.png', 'rb') as f:
    #     response = requests.post('http://localhost:3000/upload_image', files={'image': f})  # Node.js 서버 포트는 3000입니다.
    #     print(response.text)

    return "mfcc_spectrum_graph.png processed and sent to Node.js server"


@app.route('/mfcc_bar_graph', methods=['GET'])
def mfcc_bar_graph():
    global mfcc_control_data, mfcc_record_data
    # 12개 열 각각의 평균을 계산합니다.
    control_means = {}
    record_means = {}

    for column_name in mfcc_control_data.columns[0:14]:  # 첫 12개의 열에 대해 반복합니다.
        try:
            # 첫 번째 데이터프레임에서 각 열에서 숫자로 변환 가능한 값만 필터링합니다.
            control_data = pd.to_numeric(mfcc_control_data[column_name], errors='coerce')
            control_mfcc_mean = control_data.mean()
            control_means[column_name] = control_mfcc_mean

            # 두 번째 데이터프레임에서 각 열에서 숫자로 변환 가능한 값만 필터링합니다.
            record_data = pd.to_numeric(mfcc_record_data[column_name], errors='coerce')
            record_mfcc_mean = record_data.mean()
            record_means[column_name] = record_mfcc_mean
        except ValueError:
            # 변환할 수 없는 값이 있는 경우 예외 처리
            print(f'{column_name} 열에 변환할 수 없는 값이 있습니다.')

    # 각 열의 평균값을 출력합니다.
    print("\n실시간 column means:")
    for column_name, column_mean in control_means.items():
        print(f'{column_name}의 평균값은 {column_mean}입니다.')

    print("\n녹취록 column means:")
    for column_name, column_mean in record_means.items():
        print(f'{column_name}의 평균값은 {column_mean}입니다.')

    # MongoDB에 데이터 삽입
    # 현재 시간을 UTC로 구하기
    current_time = datetime.datetime.utcnow()

    record_avg_data = {
        "mfcc_record_averages": record_means,
        "timestamp": current_time
    }

    control_avg_data = {
        "mfcc_control_averages" : control_means,
        "timestamp" : current_time
    }
    control_result = control_mfcc_avg.insert_one(control_avg_data)
    record_result = record_mfcc_avg.insert_one(record_avg_data)

    print("Control MFCC averages inserted with id:", control_result.inserted_id)
    print("Record MFCC averages inserted with id:", record_result.inserted_id)

    # 막대그래프로 시각화
    labels = control_means.keys()  # x축 레이블
    means1 = control_means.values()  # 첫 번째 CSV 파일의 평균값
    means2 = record_means.values()  # 두 번째 CSV 파일의 평균값

    x = np.arange(len(labels))  # 레이블 위치
    width = 0.35  # 막대 너비

    fig, ax = plt.subplots(figsize=(12, 8))
    bars1 = ax.bar(x - width / 2, means1, width, label='실시간 파일 MFCC 평균값')
    bars2 = ax.bar(x + width / 2, means2, width, label='녹취록 파일 MFCC 평균값')

    # 레이블, 제목 및 눈금 설정
    ax.set_xlabel('MFCC 계수들')
    ax.set_ylabel('평균 값')
    ax.set_title('녹취록과 실시간 음성 파일 간 MFCC 계수 평균값 비교')
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()

    # 막대 위에 값 표시
    def add_labels(bars):
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.2f}',  # 막대 위에 표시할 텍스트
                        xy=(bar.get_x() + bar.get_width() / 2, height),  # 텍스트 위치
                        xytext=(0, 3),  # 텍스트와 막대 사이의 거리
                        textcoords="offset points",
                        ha='center', va='bottom')

    add_labels(bars1)
    add_labels(bars2)

    plt.xticks(rotation=45)
    plt.tight_layout()

    # 이미지를 메모리에 저장
    img = io.BytesIO()
    fig.savefig(img, format='png')
    img.seek(0)

    # 이미지 파일로 저장
    with open(f'images/mfcc_bar_graph_{files_control_id}.png', 'wb') as f:
        f.write(img.getbuffer())

    # Node.js 서버로 이미지 전송
    # with open(f'images/mfcc_bar_graph_{files_control_id}.png', 'rb') as f:
    #     response = requests.post('http://localhost:3000/upload_image', files={'image': f})  # Node.js 서버 포트는 3000입니다.
    #     print(response.text)

    return "mfcc_bar_graph.png processed and sent to Node.js server"

@app.route('/model_predict', methods=['GET'])
def model_predict():
    #전역 변수 선언
    global mfcc_control_test_values, mfcc_record_test_values, db, control_predicted_labels, record_predicted_labels, files_control_id, files_record_id

    control_predictions = model.predict(mfcc_control_test_values)
    control_predicted_labels = (control_predictions > 0.5).astype(int).flatten()
    control_average_prediction = np.mean(control_predicted_labels)
    print(f"실시간 음성 녹음 화자에 대한 모델의 예측값 평균 : {control_average_prediction:.4f}")

    # record_mfcc 데이터셋에서 모델 예측
    record_predictions = model.predict(mfcc_record_test_values)
    record_predicted_labels = (record_predictions > 0.5).astype(int).flatten()
    record_average_prediction = np.mean(record_predicted_labels)

    # 결과 출력
    print(f"증거 자료 녹음 화자에 대한 모델의 예측값 평균 : {record_average_prediction:.4f}")

    # 두 벡터 정의
    vector1 = np.unique(control_predictions)
    vector2 = np.unique(record_predictions)

    # 자카드 유사도 계산
    def jaccard_similarity(v1, v2):
        v1_set = set(v1)
        v2_set = set(v2)
        intersection = len(v1_set.intersection(v2_set))
        union = len(v1_set) + len(v2_set) - intersection
        return intersection / union

    # 결과 출력
    jaccard_sim = jaccard_similarity(vector1, vector2)

    #"자카드 유사도 : 두 집합의 교집합의 크기를 합집합의 크기로 나눈 값으로 계산한 것\n1에 가까울수록 두 집합이 서로 유사함, 0에 가까우면 두 집합이 서로 다름을 의미함"
    print(f"자카드 유사도: {jaccard_sim:.4f}")

    # 평균 절대 오차 계산
    mae = np.abs(control_average_prediction - record_average_prediction)

    # 유사도 점수 계산
    # 가정: 최대 MAE는 1 (예측값의 범위가 0에서 1일 때)
    max_mae = 1
    similarity_score = 1 - (mae / max_mae)

    print(f"평균 절대 오차(MAE): {mae:.4f}")
    print(f"유사도 점수: {similarity_score:.4f}")

    # 현재 시간을 UTC로 구하기
    current_time = datetime.datetime.utcnow()
    # 소수점 네 자리까지 반올림
    record_average_prediction = round(record_average_prediction, 4)
    control_average_prediction = round(control_average_prediction, 4)
    similarity_score = round(similarity_score, 4)
    jaccard_sim = round(jaccard_sim, 4)

    # 데이터 준비
    data = {
        "live_data_prediction" : record_average_prediction,
        "record_data_prediction" : control_average_prediction,
        "MAE_similarity": similarity_score * 100,  # 계산된 정확도,
        "files_record_id" : ObjectId(files_record_id), #record_files_id에 해당 하는 값
        "files_control_id" : ObjectId(files_control_id), #control_files_id에 해당하는 값
        "timestamp" : current_time
    }

    # 데이터 삽입
    result = db['results'].insert_one(data)
    return "Data inserted with record id : {}".format(result.inserted_id)

@app.route('/visual_result', methods=['GET'])
def visual_result():
    # 전역 변수 선언
    global control_predicted_labels, record_predicted_labels

    # 실제 레이블
    control_data_labels = np.ones_like(control_predicted_labels)  # control은 모두 1
    record_data_labels = np.zeros_like(record_predicted_labels)  # record는 모두 0

    # 예측값과 실제 레이블 결합
    predicted_labels = np.concatenate([control_predicted_labels, record_predicted_labels])
    actual_labels = np.concatenate([control_data_labels, record_data_labels])

    # 예측값의 분포도 시각화
    fig, ax = plt.subplots(figsize=(10, 6))

    # 예측값 분포
    ax.hist(predicted_labels, bins=np.arange(-0.5, 2, 1), alpha=0.5, label='Predicted Labels', color='blue',
            edgecolor='black')

    # 실제 레이블 분포
    ax.hist(actual_labels, bins=np.arange(-0.5, 2, 1), alpha=0.5, label='Actual Labels', color='red', edgecolor='black')

    # 축과 제목 설정
    ax.set_xticks([0, 1])
    ax.set_xticklabels(['Record (0)', 'Control (1)'])
    ax.set_xlabel('Labels')
    ax.set_ylabel('Frequency')
    ax.set_title('Distribution of Predicted and Actual Labels')
    ax.legend(loc='upper right')

    # 이미지를 메모리에 저장
    img = io.BytesIO()
    fig.savefig(img, format='png')
    img.seek(0)

    # 이미지 파일로 저장
    with open(f'visual_result_{files_control_id}.png', 'wb') as f:
        f.write(img.getbuffer())

    # Node.js 서버로 이미지 전송
    # with open(f'visual_result_{files_control_id}.png', 'rb') as f:
    #     response = requests.post('http://localhost:3000/upload_image', files={'image': f})  # Node.js 서버 포트는 3000입니다.
    #     print(response.text)

    return "visual_result.png processed and sent to Node.js server"


if __name__ == '__main__':
    # ngrok을 통해 외부 접근 가능하도록 설정
    #conf.get_default().config_path = "C:/Users/sohee/AppData/Local/ngrok/ngrok.yml"
    public_url = ngrok.connect(5000, bind_tls=True).public_url  # 포트 번호와 함께 bind_tls 옵션 설정
    print(f" * ngrok tunnel \"{public_url}\" -> \"http://127.0.0.1:5000\"")

    def run_flask():
        app.run(port=5000)

    flask_thread = Thread(target=run_flask)
    flask_thread.start()

    # Flask 서버가 시작될 시간을 기다림
    time.sleep(2)  # 필요한 경우 더 길게 조정

    print("Flask server is running and ngrok tunnel is established.")