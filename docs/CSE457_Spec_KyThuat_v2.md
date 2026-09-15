# SPEC KỸ THUẬT — v2.0

## Trợ lý Biên bản họp: Phân người nói \+ Phiên âm \+ Đánh dấu đoạn cần xem lại

### Meeting Minutes Assistant: Speaker Diarization, Transcription, and Low-Confidence Segment Flagging

| Trường | Giá trị |
| :---- | :---- |
| **Mã đồ án** | CSE457-FP |
| **STT đề tài đã đăng ký** | 4 |
| **Sinh viên** | Lỗ Anh Việt — 2351260695 (làm cá nhân) |
| **Bài báo tham chiếu** | DiCoW: Diarization-Conditioned Whisper for Target Speaker ASR (arXiv:2501.00114) |
| **Phiên bản** | 2.0 — thay thế hoàn toàn v1.0 |
| **Trạng thái** | Tài liệu vận hành chính thức. Mọi thay đổi thiết kế phải ghi vào Phụ lục A. |

> **v2.0 sửa gì so với v1.0:** nâng *đánh dấu đoạn tin cậy thấp* từ một trường dữ liệu tùy chọn thành **module M5 bắt buộc có câu hỏi nghiên cứu và metric riêng** (đây là nội dung đã cam kết trong tên đề tài); nâng **website thành bắt buộc** và đổi từ Streamlit sang Next.js \+ FastAPI; đưa **DiCoW** vào đúng vị trí (biến thể so sánh, không phải baseline); nâng **ECAPA-TDNN backend** từ tùy chọn thành bắt buộc; nâng tập tự thu lên **5–10 cuộc họp** theo gợi ý của giảng viên.

---

## MỤC LỤC

1. [Phạm vi](#1-phạm-vi)  
2. [Câu hỏi nghiên cứu](#2-câu-hỏi-nghiên-cứu)  
3. [Yêu cầu](#3-yêu-cầu)  
4. [Kiến trúc tổng thể](#4-kiến-trúc-tổng-thể)  
5. [Đặc tả định dạng dữ liệu](#5-đặc-tả-định-dạng-dữ-liệu)  
6. [Đặc tả module](#6-đặc-tả-module)  
7. [Đặc tả bộ dữ liệu](#7-đặc-tả-bộ-dữ-liệu)  
8. [Đặc tả đánh giá](#8-đặc-tả-đánh-giá)  
9. [Quan hệ với bài báo tham chiếu](#9-quan-hệ-với-bài-báo-tham-chiếu)  
10. [Cấu trúc mã nguồn](#10-cấu-trúc-mã-nguồn)  
11. [Cấu hình](#11-cấu-hình)  
12. [Kiểm thử và tiêu chí nghiệm thu](#12-kiểm-thử-và-tiêu-chí-nghiệm-thu)  
13. [Khả năng tái lập](#13-khả-năng-tái-lập)  
14. [Lộ trình](#14-lộ-trình)  
- [Phụ lục A — Nhật ký quyết định thiết kế](#phụ-lục-a--nhật-ký-quyết-định-thiết-kế)  
- [Phụ lục B — Truy vết cam kết đăng ký → đặc tả](#phụ-lục-b--truy-vết-cam-kết-đăng-ký--đặc-tả)

---

## 1\. PHẠM VI

### 1.1 Trong phạm vi

- Xử lý file audio **offline** (không realtime/streaming)  
- Audio **đơn kênh** (single-channel), thu bằng 1 microphone  
- Hội thoại **2–6 người nói**, thời lượng 3–30 phút  
- Ngôn ngữ chính: **tiếng Việt**, có xen kẽ tiếng Anh (code-switching)  
- Đầu ra: transcript gắn nhãn người nói \+ **đánh dấu đoạn cần soát lại** \+ tóm tắt \+ việc cần làm  
- **Website** cho phép tải file lên và xem/sửa kết quả

### 1.2 Ngoài phạm vi

| Không làm | Lý do |
| :---- | :---- |
| Xử lý thời gian thực | Độ phức tạp kỹ thuật vượt khung đồ án |
| Multi-channel / microphone array | Không có thiết bị, dữ liệu tiếng Việt không tồn tại |
| Nhận diện danh tính thật (đây là ai) | Chỉ phân biệt SPEAKER\_00/01/02, không định danh |
| Tách nguồn âm (source separation) | Nhắc trong "hướng phát triển" |
| Huấn luyện / fine-tune mô hình | Chỉ dùng pretrained \+ inference (xem §9.2) |
| Xác thực người dùng, đa người dùng trên web | Không phải trọng tâm môn học |

### 1.3 Giả định

- Audio đầu vào có SNR ≥ 5 dB (không phải môi trường cực ồn)  
- Số người nói ≤ 6  
- Người nói không thay đổi vị trí đột ngột  
- Người dùng chấp nhận độ trễ xử lý (RTF ≤ 2.0 là chấp nhận được)

---

## 2\. CÂU HỎI NGHIÊN CỨU

Ba câu hỏi này là xương sống của báo cáo. Mỗi thí nghiệm ở §8 phải trả lời được ít nhất một câu.

| ID | Câu hỏi | Metric trả lời | Mục thí nghiệm |
| :---- | :---- | :---- | :---- |
| **RQ1** | Hệ diarization \+ ASR tiếng Việt suy giảm ra sao khi tăng tỷ lệ chồng lấn giọng nói và mức nhiễu? | DER (2 chế độ) \+ 3 thành phần, WER, cpWER trên ma trận 9 điều kiện | §8.5 |
| **RQ2** | Bao nhiêu phần lỗi transcript cuối cùng là do lỗi diarization lan truyền sang, chứ không phải do bản thân ASR? | Δ \= cpWER\_cascaded − cpWER\_oracle, và tỷ lệ % | §8.6 |
| **RQ3** | Một heuristic độ tin cậy kết hợp tín hiệu từ **cả ASR lẫn diarization** có phát hiện được các đoạn transcript sai nhiều hơn so với chỉ dùng tín hiệu ASR đơn thuần không? | Precision/Recall/F1, đường risk–coverage, AUC | §8.7 |

> **RQ3 là phần đóng góp riêng của đồ án.** RQ1 và RQ2 là đo đạc trên hệ ghép từ mô hình pretrained; RQ3 mới là thứ do sinh viên thiết kế và có thể so sánh ablation. Đây cũng chính là nội dung đã cam kết trong tên đề tài tiếng Anh ("Low-Confidence Segment Flagging"), nên **không được cắt bỏ khi thiếu thời gian**.

---

## 3\. YÊU CẦU

### 3.1 Yêu cầu chức năng

| ID | Mô tả | Ưu tiên |
| :---- | :---- | :---- |
| **FR-01** | Nhận file audio WAV/MP3/M4A và chuẩn hóa về 16kHz mono | Bắt buộc |
| **FR-02** | Phân đoạn audio thành các lượt nói và gán nhãn người nói | Bắt buộc |
| **FR-03** | Chuyển đổi từng lượt nói thành văn bản tiếng Việt | Bắt buộc |
| **FR-04** | Tính điểm tin cậy cho từng lượt nói từ tín hiệu ASR \+ diarization | Bắt buộc |
| **FR-05** | Đánh dấu (flag) các lượt có điểm tin cậy dưới ngưỡng, kèm **lý do** bị đánh dấu | Bắt buộc |
| **FR-06** | Xuất transcript định dạng `[hh:mm:ss] SPEAKER_XX: nội dung`, đoạn bị flag có ký hiệu riêng | Bắt buộc |
| **FR-07** | Tính và báo cáo DER, WER, cpWER khi có ground truth | Bắt buộc |
| **FR-08** | Sinh dữ liệu hội thoại mô phỏng kèm ground truth | Bắt buộc |
| **FR-09** | Website: tải file lên, theo dõi tiến trình, xem kết quả | Bắt buộc |
| **FR-10** | Website: highlight trực quan đoạn cần soát lại, cho phép sửa text tại chỗ | Bắt buộc |
| **FR-11** | Tóm tắt nội dung cuộc họp và trích xuất việc cần làm bằng LLM | Bắt buộc |
| **FR-12** | Đổi tên SPEAKER\_XX thành tên thật | Nên có |
| **FR-13** | Xuất file Markdown / SRT / PDF | Nên có |
| **FR-14** | Timeline trực quan theo màu người nói | Tùy chọn |
| **FR-15** | So sánh 2 backend diarization trên cùng file trong giao diện | Tùy chọn |

> FR-04, FR-05, FR-10 là hiện thực hóa cam kết "đánh dấu các đoạn văn bản có độ tin cậy thấp để người dùng soát lại" trong bản đăng ký. FR-09 hiện thực hóa "Xây dựng website...".

### 3.2 Yêu cầu phi chức năng

| ID | Mô tả | Ngưỡng |
| :---- | :---- | :---- |
| **NFR-01** | Tốc độ xử lý | RTF ≤ 2.0 trên GPU T4 (10 phút audio ≤ 20 phút xử lý) |
| **NFR-02** | Bộ nhớ GPU | ≤ 15 GB (chạy được trên Colab free T4) |
| **NFR-03** | Độ dài audio tối đa | 30 phút/file |
| **NFR-04** | Khả năng phục hồi | Cache kết quả trung gian; lỗi ở M3 không mất kết quả M2 |
| **NFR-05** | Tái lập | Cùng seed \+ cùng config → cùng kết quả |
| **NFR-06** | Ghi log | Mọi lần chạy ghi vào `experiments.csv` |
| **NFR-07** | Tách biệt web/pipeline | Web gọi pipeline qua API; pipeline chạy độc lập được bằng CLI |

---

## 4\. KIẾN TRÚC TỔNG THỂ

### 4.1 Sơ đồ luồng dữ liệu

   audio gốc (.wav/.mp3/.m4a, sample rate bất kỳ)

              │

              ▼

   ┌──────────────────────┐

   │  M1  PREPROCESS      │  ← config: target\_sr, normalize

   └──────────┬───────────┘

              │  AudioBundle {waveform, sr=16000, duration}

              ▼

   ┌──────────────────────┐

   │  M2  DIARIZATION     │  ← config: backend, min/max\_speakers

   │  ├─ VAD              │

   │  ├─ ECAPA embedding  │

   │  └─ Clustering       │

   └──────────┬───────────┘

              │  List\[Segment\] \+ DiarMeta  →  .rttm

              ▼

   ┌──────────────────────┐

   │  M3  ASR             │  ← config: model\_name, language, batch\_size

   │  ├─ Cắt/lọc segment  │

   │  ├─ Transcribe       │

   │  └─ Thu tín hiệu ASR │     (avg\_logprob, no\_speech\_prob, ...)

   └──────────┬───────────┘

              │  List\[Utterance\]  →  .json

              ▼

   ┌──────────────────────┐

   │  M4  POSTPROCESS     │  ← config: merge\_gap

   │  ├─ Gộp turn         │

   │  └─ Chuẩn hóa text   │

   └──────────┬───────────┘

              │  List\[Turn\]

              ▼

   ┌──────────────────────┐

   │  M5  CONFIDENCE ⭐   │  ← config: weights, threshold

   │  ├─ Tín hiệu ASR     │

   │  ├─ Tín hiệu diar.   │

   │  ├─ Điểm tổng hợp    │

   │  └─ Gắn cờ \+ lý do   │

   └──────────┬───────────┘

              │  List\[Turn\] (đã có confidence \+ flags)

              ▼

   ┌──────────────────────┐

   │  M6  LLM             │  ← config: llm\_model

   │  └─ Tóm tắt \+ việc   │

   └──────────┬───────────┘

              │  MeetingMinutes

              ▼

   ┌──────────────────────┐        ┌──────────────────────────┐

   │  M7  WEB / EXPORT    │        │  M8  EVALUATION          │

   │  FastAPI \+ Next.js   │        │  DER / WER / cpWER       │

   └──────────────────────┘        │  \+ đánh giá flagging     │

                                   └──────────────────────────┘

                                        ▲

                              ground truth (.rttm \+ .json)

### 4.2 Nguyên tắc thiết kế

| Nguyên tắc | Áp dụng |
| :---- | :---- |
| **Mỗi module là một hàm thuần** | Input → Output, không giữ trạng thái toàn cục |
| **Ghi ra đĩa giữa các module** | Chạy lại M3 không cần chạy lại M2 |
| **Backend thay thế được** | M2 có 2 cài đặt dùng chung interface |
| **Cấu hình tách khỏi code** | Mọi tham số nằm trong YAML, không hardcode |
| **Pipeline không biết đến web** | `src/` không import gì từ `api/` hay `web/` |
| **Tín hiệu tin cậy thu tại nguồn** | M2 và M3 phải *ghi lại* tín hiệu thô ngay lúc chạy; M5 chỉ tổng hợp, không tính lại |

> Nguyên tắc cuối rất quan trọng: nếu M3 vứt bỏ `avg_logprob` thì M5 không có cách nào lấy lại mà không chạy lại toàn bộ ASR.

---

## 5\. ĐẶC TẢ ĐỊNH DẠNG DỮ LIỆU

### 5.1 Kiểu dữ liệu nội bộ

from dataclasses import dataclass, field

from typing import Optional, List, Dict

@dataclass

class Segment:

    """Một đoạn có tiếng nói, đã gán người nói. Đơn vị: giây."""

    start: float          \# \>= 0

    end: float            \# \> start

    speaker: str          \# "SPEAKER\_00", "SPEAKER\_01", ...

    @property

    def duration(self) \-\> float:

        return self.end \- self.start

@dataclass

class DiarSignals:

    """Tín hiệu độ chắc chắn do M2 sinh ra cho từng segment. Đầu vào của M5."""

    overlap\_ratio: float          \# \[0,1\] tỷ lệ thời gian chồng lấn speaker khác

    cluster\_margin: Optional\[float\] \= None   \# d(nearest other centroid) \- d(own centroid)

    n\_windows: Optional\[int\] \= None          \# số cửa sổ embedding tạo nên segment

@dataclass

class ASRSignals:

    """Tín hiệu độ chắc chắn do M3 sinh ra. Đầu vào của M5."""

    avg\_logprob: Optional\[float\] \= None       \# Whisper: thường trong \[-1.0, \-0.1\]

    no\_speech\_prob: Optional\[float\] \= None    \# \[0,1\]

    compression\_ratio: Optional\[float\] \= None \# \> 2.4 ⇒ nghi ảo giác/lặp

    min\_token\_logprob: Optional\[float\] \= None

    was\_split: bool \= False                   \# segment đã bị cắt nhỏ ở M3

@dataclass

class Utterance(Segment):

    """Segment đã có nội dung văn bản."""

    text: str

    asr: ASRSignals \= field(default\_factory=ASRSignals)

    diar: DiarSignals \= None

@dataclass

class Turn:

    """Nhiều Utterance liên tiếp cùng một người, đã gộp."""

    start: float

    end: float

    speaker: str

    text: str

    utterances: List\[Utterance\]

    confidence: Optional\[float\] \= None        \# \[0,1\] do M5 tính

    flagged: bool \= False                     \# do M5 quyết định

    flag\_reasons: List\[str\] \= field(default\_factory=list)

@dataclass

class MeetingMinutes:

    """Kết quả cuối cùng."""

    audio\_id: str

    duration: float

    num\_speakers: int

    turns: List\[Turn\]

    flagged\_ratio: float \= 0.0                \# % thời lượng bị gắn cờ

    summary: Optional\[str\] \= None

    action\_items: Optional\[List\[dict\]\] \= None

### 5.2 Định dạng RTTM (chuẩn NIST)

Dùng cho cả ground truth và kết quả dự đoán của M2.

SPEAKER \<file-id\> \<ch\> \<start\> \<duration\> \<NA\> \<NA\> \<speaker-id\> \<NA\> \<NA\>

Ví dụ:

SPEAKER meeting\_001 1 0.500 3.240 \<NA\> \<NA\> SPEAKER\_00 \<NA\> \<NA\>

SPEAKER meeting\_001 1 4.100 2.870 \<NA\> \<NA\> SPEAKER\_01 \<NA\> \<NA\>

SPEAKER meeting\_001 1 6.550 1.920 \<NA\> \<NA\> SPEAKER\_00 \<NA\> \<NA\>

**Ràng buộc bắt buộc:**

- `start` và `duration` làm tròn **3 chữ số thập phân** (mili-giây)  
- Trường thứ 3 (channel) luôn là `1`  
- Các trường `<NA>` giữ nguyên chữ, không để trống  
- Phân cách bằng **dấu cách**, không phải tab  
- Segment có thể chồng lấn nhau — đây là điều bình thường

>   
> ⚠️ **Lỗi hay gặp:** Ghi `duration` nhưng lại truyền vào giá trị `end`. Đây là lỗi phổ biến nhất và làm DER tăng vọt lên \>60% mà không báo lỗi gì.  
>   
> ⚠️ RTTM **không có chỗ** cho tín hiệu tin cậy. Tín hiệu của M2 lưu song song ở `{audio_id}.diarsignals.json`, khóa theo `(start, end, speaker)` làm tròn 3 chữ số.

### 5.3 Định dạng transcript JSON

Đầu ra của M3, đầu vào của M4/M5/M8.

{

  "audio\_id": "meeting\_001",

  "duration": 300.0,

  "sample\_rate": 16000,

  "num\_speakers": 3,

  "config\_hash": "a3f9c21e",

  "utterances": \[

    {

      "start": 0.500,

      "end": 3.740,

      "speaker": "SPEAKER\_00",

      "text": "chào mọi người, hôm nay mình họp về tiến độ đồ án",

      "asr": {

        "avg\_logprob": \-0.24,

        "no\_speech\_prob": 0.02,

        "compression\_ratio": 1.41,

        "min\_token\_logprob": \-0.88,

        "was\_split": false

      },

      "diar": {

        "overlap\_ratio": 0.0,

        "cluster\_margin": 0.31,

        "n\_windows": 4

      }

    }

  \]

}

### 5.4 Định dạng biên bản xuất ra

\# Biên bản họp — meeting\_001

\*\*Thời lượng:\*\* 05:00 | \*\*Số người nói:\*\* 3 | \*\*Cần soát lại:\*\* 12.4% thời lượng

\#\# Tóm tắt

...

\#\# Việc cần làm

\- \[ \] \*\*Việt\*\* — hoàn thành module diarization — hạn: 20/09

\#\# Nội dung chi tiết

\*\*\[00:00:00\] SPEAKER\_00:\*\* chào mọi người, hôm nay mình họp về tiến độ đồ án

\*\*\[00:00:04\] SPEAKER\_01:\*\* ⚠️ ok mình đã xong phần data pipeline rồi

    └ \*cần soát lại: chồng lấn 42%, độ tin cậy ASR thấp\*

---

## 6\. ĐẶC TẢ MODULE

### M1 — Tiền xử lý

**Interface**

def preprocess(

    path: str,

    target\_sr: int \= 16000,

    normalize: bool \= True,

    denoise: bool \= False

) \-\> AudioBundle

**Xử lý**

1. Đọc bằng `librosa.load(path, sr=None, mono=False)` — giữ sr gốc để log  
2. Nếu stereo → mono bằng **trung bình cộng các kênh** (không lấy kênh trái)  
3. Resample về 16000 Hz bằng `soxr_hq`  
4. Nếu `normalize`: chuẩn hóa loudness về **−23 LUFS**, hoặc peak normalize về −1 dBFS nếu không có `pyloudnorm`  
5. Ép kiểu `float32`, giá trị trong \[−1, 1\]

**Ca biên**

| Tình huống | Xử lý |
| :---- | :---- |
| File \> 30 phút | Cảnh báo, vẫn xử lý, ghi log |
| File \< 5 giây | Ném `ValueError` |
| Audio toàn im lặng (max amplitude \< 1e-4) | Ném `ValueError` |
| Sample rate \< 16kHz | Upsample nhưng **cảnh báo rõ**: chất lượng ASR sẽ giảm |
| File hỏng / không đọc được | Ném `IOError` với tên file |

**Kiểm tra bắt buộc sau khi chạy**

assert audio.sr \== 16000

assert audio.waveform.ndim \== 1

assert audio.waveform.dtype \== np.float32

assert np.abs(audio.waveform).max() \<= 1.0

---

### M2 — Diarization

**Interface chung cho cả 2 backend**

class DiarizationBackend(Protocol):

    def diarize(

        self,

        audio: AudioBundle,

        min\_speakers: Optional\[int\] \= None,

        max\_speakers: Optional\[int\] \= None,

    ) \-\> tuple\[List\[Segment\], Dict\[tuple, DiarSignals\]\]: ...

> Interface trả về **cặp** (segments, signals) — khác v1.0. Backend nào không tính được `cluster_margin` thì trả `None` cho trường đó, nhưng `overlap_ratio` là **bắt buộc** vì tính được từ chính danh sách segment.

#### Backend A — `PyannoteBackend` (đường cơ sở)

| Thuộc tính | Giá trị |
| :---- | :---- |
| Model | `pyannote/speaker-diarization-3.1` |
| Yêu cầu | HuggingFace token, đã accept điều khoản |
| Đầu ra | `pyannote.core.Annotation` → convert sang `List[Segment]` |

pipeline \= Pipeline.from\_pretrained(

    "pyannote/speaker-diarization-3.1",

    use\_auth\_token=HF\_TOKEN

)

pipeline.to(torch.device("cuda"))

annotation \= pipeline(

    {"waveform": torch.from\_numpy(wav).unsqueeze(0), "sample\_rate": 16000},

    min\_speakers=min\_speakers,

    max\_speakers=max\_speakers,

)

`cluster_margin` không lấy được từ pipeline đóng gói → trả `None`.

#### Backend B — `EcapaBackend` (bắt buộc, là pipeline được đăng ký)

Pipeline 4 bước:

| Bước | Công cụ | Tham số |
| :---- | :---- | :---- |
| 1\. VAD | Silero VAD | `threshold=0.5`, `min_speech_duration_ms=250`, `min_silence_duration_ms=100` |
| 2\. Cửa sổ trượt | — | `window=1.5s`, `hop=0.75s` |
| 3\. Embedding | `speechbrain/spkrec-ecapa-voxceleb` | vector 192 chiều |
| 4\. Clustering | AHC, `metric=cosine`, `linkage=average` | `distance_threshold=0.7` (cần tinh chỉnh) |

Sau clustering: gộp các cửa sổ liền kề cùng cluster thành segment.

**Backend B phải xuất `cluster_margin`:** với mỗi cửa sổ, tính khoảng cách cosine tới centroid của cụm được gán và tới centroid gần nhất trong các cụm còn lại; `margin = d_other − d_own`. Margin của segment \= trung bình các cửa sổ cấu thành. Margin nhỏ ⇒ mô hình lưỡng lự giữa hai người ⇒ tín hiệu quý cho M5.

> Đây là lý do Backend B là **bắt buộc chứ không tùy chọn**: nó là backend duy nhất cho được `cluster_margin`, mà ablation của RQ3 cần tín hiệu này. Ngoài ra ECAPA-TDNN \+ clustering chính là pipeline đã đăng ký với giảng viên.

**Ca biên chung cho cả 2 backend**

| Tình huống | Xử lý |
| :---- | :---- |
| Không phát hiện tiếng nói nào | Trả về list rỗng, ghi log cảnh báo |
| Chỉ phát hiện 1 người | Hợp lệ, không phải lỗi |
| Segment ngắn hơn 0.3s | Loại bỏ (quá ngắn để ASR xử lý) |
| Segment dài hơn 30s | Giữ nguyên ở M2, M3 sẽ tự cắt nhỏ |
| Hai segment cùng speaker cách nhau \< 0.2s | Giữ riêng ở M2, gộp ở M4 |

**Tiêu chí nghiệm thu M2**

- Backend A: DER trên file mẫu AMI sai lệch không quá ±5% so với con số công bố của pyannote  
- Backend B: DER trên dữ liệu mô phỏng điều kiện sạch/0% overlap ≤ 15%  
- RTTM xuất ra đọc được bằng `pyannote.metrics` không báo lỗi định dạng  
- `overlap_ratio` tính ra khớp với tỷ lệ overlap thiết kế của dữ liệu mô phỏng (sai số \< 3%)

---

### M3 — ASR

**Interface**

def transcribe(

    audio: AudioBundle,

    segments: List\[Segment\],

    diar\_signals: Dict\[tuple, DiarSignals\],

    model\_name: str \= "vinai/PhoWhisper-medium",

    language: str \= "vi",

    batch\_size: int \= 8,

    max\_segment\_sec: float \= 28.0,

    min\_segment\_sec: float \= 0.3,

    masking: str \= "none",          \# "none" | "input\_masking"  (xem §9)

) \-\> List\[Utterance\]

**Xử lý**

1. **Lọc segment:** bỏ segment ngắn hơn `min_segment_sec`  
2. **Cắt segment dài:** segment \> `max_segment_sec` → chia nhỏ tại điểm im lặng gần nhất; nếu không tìm được thì cắt cứng với **overlap 0.5s**, đặt `was_split=True`  
3. **Đệm biên:** mở rộng mỗi segment thêm **0.1s** hai đầu để tránh cụt âm đầu/cuối từ  
4. **Batch inference:** nhóm các segment độ dài tương đương để giảm padding  
5. **Thu tín hiệu:** lưu `avg_logprob`, `no_speech_prob`, `compression_ratio`, `min_token_logprob` vào `ASRSignals` — **bắt buộc, không được bỏ**  
6. **Gắn kèm tín hiệu diarization:** copy `DiarSignals` tương ứng vào từng Utterance  
7. **Ghép lại:** với segment bị cắt nhỏ, nối text, loại phần lặp ở vùng overlap; `avg_logprob` lấy trung bình có trọng số theo thời lượng

**Cấu hình sinh**

generate\_kwargs \= {

    "language": "vi",

    "task": "transcribe",

    "no\_repeat\_ngram\_size": 3,     \# chống lặp vô hạn

    "temperature": 0.0,            \# deterministic, phục vụ tái lập

    "return\_dict\_in\_generate": True,

    "output\_scores": True,         \# cần cho min\_token\_logprob

}

**Model:** mặc định `vinai/PhoWhisper-medium`. Chạy thêm `openai/whisper-large-v3-turbo` trên một tập con để so sánh (đề tài đăng ký ghi "Whisper/PhoWhisper"), báo cáo bảng đối chiếu WER.

**Ca biên**

| Tình huống | Xử lý |
| :---- | :---- |
| Lặp vô hạn một cụm từ | `no_repeat_ngram_size=3`; nếu số từ \> 3× kỳ vọng theo thời lượng → `compression_ratio` cao, để M5 gắn cờ |
| Segment chỉ có tiếng ồn | Lọc bằng danh sách đen ảo giác dưới đây |
| Segment chồng lấn 2 người | Vẫn transcribe riêng từng segment; `overlap_ratio` đã ghi lại để M5 dùng |
| OOM khi batch lớn | Bắt exception, giảm `batch_size` một nửa và thử lại |

**Danh sách đen text ảo giác**

HALLUCINATION\_BLACKLIST \= \[

    "cảm ơn các bạn đã xem",

    "hãy đăng ký kênh",

    "phụ đề được thực hiện bởi",

    "hẹn gặp lại các bạn",

\]

Utterance khớp danh sách đen: **không xóa**, mà đặt text về rỗng và thêm lý do `"hallucination_blacklist"` để M5 gắn cờ. Xóa thẳng sẽ làm sai phép đo WER (biến lỗi insertion thành deletion).

---

### M4 — Hậu xử lý

**Interface**

def postprocess(

    utterances: List\[Utterance\],

    merge\_gap: float \= 0.8,

    remove\_fillers: bool \= False,

) \-\> List\[Turn\]

**Bước 1 — Gộp turn.** Gộp hai utterance liên tiếp nếu cùng `speaker` VÀ `next.start − prev.end ≤ merge_gap` (mặc định 0.8s).

**Bước 2 — Chuẩn hóa văn bản.**

- Viết hoa đầu câu  
- Chuyển số đọc thành số viết ở nơi rõ ràng ("hai mươi tháng chín" → "20/9")  
- Loại bỏ từ đệm ("ừ", "à", "kiểu") — **mặc định tắt**, vì đo WER phải dùng bản chưa lọc

>   
> M4 **không** tính confidence. Turn sau M4 có `confidence=None`. Việc tổng hợp tín hiệu là của M5, để có thể chạy lại M5 với trọng số khác mà không cần chạy lại gì.

---

### M5 — Chấm điểm tin cậy và gắn cờ ⭐

Module trung tâm của RQ3. Đây là phần tự thiết kế, không có thư viện làm sẵn.

**Interface**

def score\_confidence(

    turns: List\[Turn\],

    weights: Dict\[str, float\],

    threshold: float,

) \-\> List\[Turn\]        \# đã điền confidence, flagged, flag\_reasons

**Bước 1 — Chuẩn hóa từng tín hiệu về \[0,1\]**, 1 \= đáng tin.

| Tín hiệu | Nguồn | Công thức | Ghi chú |
| :---- | :---- | :---- | :---- |
| `c_asr` | `avg_logprob` | `clip((avg_logprob + 1.0) / 0.9, 0, 1)` | avg\_logprob thực tế nằm khoảng \[−1.0, −0.1\] |
| `c_speech` | `no_speech_prob` | `1 − no_speech_prob` | cao ⇒ có thể là im lặng bị phiên âm bừa |
| `c_rep` | `compression_ratio` | `1` nếu ≤ 2.4, ngược lại `clip(2.4/cr, 0, 1)` | ngưỡng 2.4 theo thông lệ Whisper |
| `c_ovl` | `overlap_ratio` | `1 − overlap_ratio` | tín hiệu **từ diarization** |
| `c_spk` | `cluster_margin` | `clip(margin / margin_ref, 0, 1)`, `margin_ref` \= phân vị 90 trên tập dev | tín hiệu **từ diarization** |
| `c_dur` | `duration` | `clip(duration / 1.5, 0, 1)` | đoạn quá ngắn khó phiên âm đúng |

Tín hiệu `None` (backend không cung cấp): loại khỏi tổng và **chuẩn hóa lại trọng số**, không thay bằng 0 — thiếu tín hiệu không đồng nghĩa kém tin cậy.

**Bước 2 — Điểm tổng hợp**

confidence \= Σ wᵢ · cᵢ  /  Σ wᵢ         (chỉ tính các cᵢ khả dụng)

Trọng số mặc định (ghi trong YAML, sẽ tinh chỉnh trên tập dev):

w\_asr: 0.30

w\_speech: 0.10

w\_rep: 0.10

w\_ovl: 0.25

w\_spk: 0.15

w\_dur: 0.10

**Bước 3 — Gắn cờ và giải thích.** `flagged = confidence < threshold`. Với mỗi tín hiệu có `cᵢ < 0.5`, thêm một lý do đọc được vào `flag_reasons`:

| Tín hiệu yếu | Lý do hiển thị |
| :---- | :---- |
| `c_ovl` | `"chồng lấn {overlap_ratio:.0%}"` |
| `c_asr` | `"độ tin cậy ASR thấp"` |
| `c_rep` | `"nghi lặp/ảo giác"` |
| `c_spk` | `"khó phân biệt người nói"` |
| `c_dur` | `"đoạn quá ngắn"` |
| `c_speech` | `"nghi không có tiếng nói"` |

> Yêu cầu hiển thị lý do là có chủ đích: một điểm số trần trụi không giúp người dùng biết nên sửa gì. Đây cũng là phần dễ trình bày khi bảo vệ.

**Bước 4 — Chọn ngưỡng.** `threshold` **không** đặt tùy tiện. Chọn trên tập dev mô phỏng theo *coverage mục tiêu*: ngưỡng nhỏ nhất sao cho tổng thời lượng bị gắn cờ ≤ 20% (giả định người dùng chỉ đủ kiên nhẫn soát lại 1/5 cuộc họp). Ghi ngưỡng đã chọn và coverage thực tế vào `experiments.csv`.

**Đường cơ sở để so sánh (bắt buộc, phục vụ ablation RQ3):**

| Tên | Định nghĩa |
| :---- | :---- |
| `baseline_asr_only` | Chỉ dùng `c_asr` — đại diện cho cách làm ngây thơ nhất |
| `baseline_random` | Gắn cờ ngẫu nhiên cùng coverage — cận dưới |
| `full` | Toàn bộ 6 tín hiệu |
| `no_diar` | Bỏ `c_ovl` và `c_spk` — chứng minh giá trị của tín hiệu diarization |

**Tiêu chí nghiệm thu M5:** `full` phải có F1 cao hơn `baseline_asr_only` một cách rõ rệt trên ít nhất 6/9 điều kiện. Nếu không đạt, đó **vẫn là một kết quả hợp lệ để báo cáo** — nhưng phải phân tích nguyên nhân, không được giấu.

---

### M6 — LLM tóm tắt

**Interface**

def summarize(turns: List\[Turn\], llm\_model: str) \-\> tuple\[str, List\[dict\]\]

**Prompt**

Bạn là trợ lý ghi biên bản họp. Dưới đây là transcript có gắn nhãn người nói.

Một số đoạn được đánh dấu \[?\] nghĩa là độ tin cậy phiên âm thấp.

{transcript}

Hãy trả về JSON với cấu trúc chính xác sau, không thêm markdown hay giải thích:

{

  "summary": "tóm tắt 3-5 câu",

  "topics": \["chủ đề 1", "chủ đề 2"\],

  "action\_items": \[

    {"speaker": "SPEAKER\_00", "task": "...", "deadline": "... hoặc null", "uncertain": false}

  \]

}

Chỉ trích action item khi transcript nêu rõ. Không suy diễn.

Nếu action item dựa trên đoạn có \[?\], đặt "uncertain": true.

**Ca biên**

| Tình huống | Xử lý |
| :---- | :---- |
| Transcript dài vượt context | Chia đoạn, tóm tắt từng phần rồi tóm tắt lại (map-reduce) |
| LLM trả JSON sai định dạng | Parse; thất bại thì gọi lại 1 lần kèm lời nhắc sửa; vẫn thất bại thì `summary=None` |
| Không có action item | Trả mảng rỗng, không bịa |

---

### M7 — Web

**Kiến trúc:** `Next.js (App Router, TypeScript, Tailwind)` ⇄ `FastAPI` ⇄ `src/pipeline.py`

Xử lý chạy nền (background task), frontend hỏi trạng thái theo chu kỳ (polling).

**API**

| Method | Route | Mô tả |
| :---- | :---- | :---- |
| `POST` | `/api/jobs` | Nhận file audio, trả `job_id`, chạy pipeline nền |
| `GET` | `/api/jobs/{id}` | Trạng thái: `stage` (M1–M6), `progress`, `error` |
| `GET` | `/api/jobs/{id}/result` | Trả `MeetingMinutes` dạng JSON |
| `PATCH` | `/api/jobs/{id}/turns/{idx}` | Sửa text hoặc tên speaker |
| `GET` | `/api/jobs/{id}/export?fmt=md|srt|pdf` | Xuất file |

**Màn hình**

\[Upload\]  →  \[Đang xử lý...\]  →  \[Kết quả\]

                  │                   ├─ Tab: Biên bản (đoạn flag có nền vàng \+ tooltip lý do)

              thanh tiến trình         ├─ Tab: Timeline theo màu người nói

              theo từng module         ├─ Tab: Chỉ số (nếu có ground truth)

                                       └─ Đổi tên người nói / Sửa text / Xuất file

**Thành phần bắt buộc**

| Thành phần | Mô tả |
| :---- | :---- |
| File uploader | .wav/.mp3/.m4a, tối đa 200MB |
| Progress bar | 6 giai đoạn tương ứng M1–M6 |
| Transcript view | Mỗi turn một dòng, nền màu theo speaker |
| **Flag highlight** | Đoạn `flagged=true` có nền cảnh báo \+ tooltip liệt kê `flag_reasons` |
| **Inline editor** | Click vào đoạn để sửa text; sửa xong bỏ cờ |
| Speaker renamer | Ô nhập text cho từng SPEAKER\_XX |
| Export button | Markdown / SRT / PDF |

**Tiêu chí nghiệm thu M7:** upload → xem → sửa một đoạn bị flag → xuất file, chạy end-to-end trên 3 file khác nhau, bản sửa được phản ánh đúng trong file xuất ra.

---

### M8 — Đánh giá

Xem §8. Chạy độc lập bằng CLI, không qua web.

---

## 7\. ĐẶC TẢ BỘ DỮ LIỆU

### 7.1 Nguồn dữ liệu

| Tên | Dùng để | Ghi chú |
| :---- | :---- | :---- |
| VIVOS (**test split**) | Sinh hội thoại mô phỏng | Giọng đọc, 46 người nói |
| VietnamCeleb / VoxVietnam | Đa dạng giọng (tùy chọn) | Gần hội thoại thật hơn |
| MUSAN (noise subset) | Thêm nhiễu nền |  |
| RIR corpus | Mô phỏng tiếng vọng phòng |  |
| **Tự thu: 5–10 cuộc họp** | Tập test thật | Mỗi cuộc 10–20 phút, 3–5 người |
| AMI (1 file mẫu) | Mốc neo kiểm chứng M2 | Không dùng để báo cáo kết quả chính |

> **Quan trọng:** Chỉ dùng **test split** của VIVOS để tránh trùng dữ liệu huấn luyện của PhoWhisper.  
>   
> Tập tự thu 5–10 cuộc theo đúng gợi ý của giảng viên. Chỉ cần gán nhãn tay **2–3 cuộc** (mỗi cuộc 5 phút đầu) để có ground truth đối chiếu; số còn lại dùng để kiểm tra định tính và làm demo trên web. Gán nhãn tay bằng Audacity/ELAN, xuất RTTM.

### 7.2 Ma trận điều kiện (dữ liệu mô phỏng)

| Chiều | Các mức | Số mức |
| :---- | :---- | :---- |
| Tỷ lệ chồng lấn | 0%, 15%, 30% | 3 |
| Nhiễu | sạch, SNR 15dB, SNR 5dB | 3 |
| Số người nói | 2, 3, 4 | 3 |

**Bộ chính (RQ1, RQ2, RQ3):** 3 overlap × 3 nhiễu \= **9 điều kiện** × 20 phiên \= **180 phiên**, cố định 3 người nói. **Bộ phụ:** 3 mức số người nói × 20 phiên \= 60 phiên, cố định sạch/overlap 15%. **Tập dev để tinh chỉnh trọng số và ngưỡng M5:** 30 phiên riêng, **không** nằm trong 180 phiên báo cáo.

Mỗi phiên **3–5 phút**. Tổng ≈ 18 giờ audio, ≈ 7 GB.

> Tách tập dev là bắt buộc. Tinh chỉnh trọng số M5 rồi báo cáo trên chính tập đó là rò rỉ dữ liệu — lỗi này rất dễ bị hỏi khi bảo vệ.

### 7.3 Quy ước đặt tên file

sim\_{ovl}\_{noise}\_{nspk}\_{index}.wav

Ví dụ: `sim_ovl15_snr15_spk3_007.wav`

Mỗi phiên có 3 file đi kèm:

sim\_ovl15\_snr15\_spk3\_007.wav      \# audio

sim\_ovl15\_snr15\_spk3\_007.rttm     \# ground truth diarization

sim\_ovl15\_snr15\_spk3\_007.json     \# ground truth transcript

### 7.4 Ràng buộc thuật toán sinh dữ liệu

| Ràng buộc | Giá trị |
| :---- | :---- |
| Không cho cùng một người nói 2 lượt liên tiếp | Bắt buộc |
| Khoảng lặng giữa 2 lượt (không overlap) | Uniform(0.1s, 1.0s) |
| Độ chồng lấn khi có overlap | Uniform(0.2s, min(1.5s, 0.5 × độ dài câu)) |
| Sai số tỷ lệ overlap thực tế vs mục tiêu | ≤ 3% tuyệt đối |
| Chống clipping | Chuẩn hóa sau khi trộn về peak −3 dBFS |
| Seed ngẫu nhiên | Ghi vào metadata, cố định để tái lập |

**Kiểm tra bắt buộc sau khi sinh (viết thành unit test):**

assert abs(measure\_overlap\_ratio(rttm) \- target\_overlap) \< 0.03

assert all(seg.end \> seg.start \>= 0 for seg in segments)

assert max(seg.end for seg in segments) \<= audio\_duration \+ 0.01

assert len(set(seg.speaker for seg in segments)) \== n\_speakers

assert np.abs(waveform).max() \< 0.999

---

## 8\. ĐẶC TẢ ĐÁNH GIÁ

### 8.1 DER — Diarization Error Rate

DER \= (T\_miss \+ T\_falsealarm \+ T\_confusion) / T\_total\_speech

**Hai chế độ chấm điểm — phải báo cáo CẢ HAI:**

| Chế độ | Collar | Tính vùng overlap | Ý nghĩa |
| :---- | :---- | :---- | :---- |
| **Nới lỏng** | 0.25s | Không | Chuẩn dùng trong hầu hết bài báo — dễ so sánh với công bố khác |
| **Nghiêm ngặt** | 0.0s | Có | Phản ánh đúng thực tế — con số xấu hơn nhiều |

**Bắt buộc tách 3 thành phần:** `miss`, `false_alarm`, `confusion`. Công cụ: `pyannote.metrics.diarization.DiarizationErrorRate`.

### 8.2 WER / CER

Công cụ: `jiwer`.

def normalize\_for\_wer(text: str) \-\> str:

    text \= text.lower()

    text \= remove\_punctuation(text)        \# . , \! ? ; : " '

    text \= collapse\_whitespace(text)

    text \= unicodedata.normalize("NFC", text)   \# thống nhất tổ hợp dấu tiếng Việt

    return text.strip()

> ⚠️ Tiếng Việt có 2 cách mã hóa dấu (NFC/NFD). Cùng chữ "ế" có thể là 1 hoặc 2 code point. Không chuẩn hóa NFC → WER cao giả tạo.

### 8.3 cpWER

**Concatenated minimum-Permutation WER:** nối toàn bộ văn bản của từng người nói, thử mọi hoán vị ánh xạ speaker dự đoán ↔ speaker thật, lấy WER nhỏ nhất. Thư viện: **`meeteval`** (khuyến nghị dùng thay vì tự cài).

### 8.4 WER theo từng turn (cần cho RQ3)

Để đánh giá M5 cần biết *turn nào thật sự sai*. Với mỗi turn dự đoán:

1. Ánh xạ turn dự đoán ↔ đoạn ground truth theo độ chồng lấn thời gian lớn nhất  
2. Tính WER cục bộ trên cặp đó  
3. Gán nhãn nhị phân: `is_bad = (wer_turn > τ)`, mặc định **τ \= 0.30**

Báo cáo thêm với τ \= 0.20 và 0.50 để chứng minh kết luận không phụ thuộc một ngưỡng cụ thể.

### 8.5 Thí nghiệm 1 — Suy giảm hiệu năng (RQ1)

Chạy toàn bộ 9 điều kiện × 2 backend diarization. Bảng cần điền:

| Overlap | Nhiễu | Backend | DER nới | DER nghiêm | Miss | FA | Conf | WER | cpWER |
| :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- | :---- |
| 0% | sạch | pyannote |  |  |  |  |  |  |  |
| 0% | sạch | ecapa |  |  |  |  |  |  |  |
| ... |  |  |  |  |  |  |  |  |  |

### 8.6 Thí nghiệm 2 — Lan truyền lỗi (RQ2)

| Điều kiện | Segment đưa vào M3 | Ký hiệu |
| :---- | :---- | :---- |
| Oracle | Ground truth RTTM | `cpWER_oracle` |
| Cascaded | RTTM dự đoán từ M2 | `cpWER_cascaded` |

Lan truyền lỗi tuyệt đối \= cpWER\_cascaded − cpWER\_oracle

Tỷ lệ lỗi do diarization  \= (cpWER\_cascaded − cpWER\_oracle) / cpWER\_cascaded × 100%

Kỳ vọng: tỷ lệ lỗi do diarization tăng mạnh khi overlap tăng.

> ⚠️ **Không** bật `input_masking` trong thí nghiệm này. Xem §9.

### 8.7 Thí nghiệm 3 — Chất lượng gắn cờ (RQ3) ⭐

Coi bài toán như phát hiện nhị phân: positive \= turn có `is_bad = true` (§8.4).

**Metric chính**

| Metric | Ý nghĩa |
| :---- | :---- |
| Precision | Trong các đoạn bị gắn cờ, bao nhiêu % thật sự sai — đo mức làm phiền người dùng |
| Recall | Trong các đoạn thật sự sai, bao nhiêu % được gắn cờ — đo mức bỏ sót |
| F1 | Cân bằng hai chỉ số trên |
| **AUC risk–coverage** | Không phụ thuộc ngưỡng, dùng để so 4 biến thể |

**Đường risk–coverage** (biểu đồ chính của phần này): sắp xếp turn theo confidence tăng dần; với mỗi mức coverage *c* (giả sử người dùng soát lại *c*% thời lượng, ưu tiên đoạn confidence thấp nhất), tính WER còn lại sau khi *giả định các đoạn được soát đều được sửa đúng*. Vẽ WER còn lại theo *c*. Đường thấp hơn \= heuristic tốt hơn.

**Bảng ablation cần điền**

| Biến thể | Precision | Recall | F1 | AUC | WER còn lại @ coverage 20% |
| :---- | :---- | :---- | :---- | :---- | :---- |
| `baseline_random` |  |  |  |  |  |
| `baseline_asr_only` |  |  |  |  |  |
| `no_diar` |  |  |  |  |  |
| `full` |  |  |  |  |  |

**Một câu kết luận dễ hiểu để đưa vào báo cáo và slide:** "Nếu người dùng chỉ soát lại 20% thời lượng cuộc họp do hệ thống chỉ ra, WER giảm từ X% xuống Y%; nếu chọn ngẫu nhiên 20% thì chỉ giảm xuống Z%."

---

## 9\. QUAN HỆ VỚI BÀI BÁO THAM CHIẾU

Bài báo đăng ký: **DiCoW — Diarization-Conditioned Whisper** (arXiv:2501.00114).

### 9.1 Bài báo dùng để làm gì

| Nội dung | Cách sử dụng trong đồ án |
| :---- | :---- |
| Đặt vấn đề speaker-attributed ASR | Nền tảng cho phần "Tổng quan" của báo cáo |
| Phân loại 3 hướng tiếp cận (độc lập / cascaded / TS-ASR) | Định vị đồ án: hướng cascaded, có lý do rõ ràng |
| Chỉ ra hạn chế của cascaded (lỗi diarization lan truyền) | Chính là động cơ của RQ2 |
| **Kỹ thuật Input Masking** | Cài đặt như một **biến thể so sánh** (xem 9.3) |
| FDDT, QK-biasing, CTC head, Co-Attention | Chỉ trình bày ở phần "Tổng quan" và "Hướng phát triển" — **không cài đặt** |
| Nhận định về rủi ro của dữ liệu tổng hợp | Trích dẫn khi bàn về hạn chế của việc đánh giá trên dữ liệu mô phỏng |

### 9.2 Vì sao không cài đặt FDDT

FDDT và QK-biasing đều đòi hỏi **fine-tune Whisper** qua ba giai đoạn trên dữ liệu hội thoại nhiều người nói **có nhãn**. Tiếng Việt không có bộ dữ liệu như vậy công khai, và §1.2 đã loại việc huấn luyện khỏi phạm vi. Checkpoint tác giả công bố là fine-tune cho tiếng Anh, không dùng lại được. Đây là một **hạn chế được nêu rõ**, không phải chỗ né tránh — và là hướng phát triển tự nhiên nếu sau này có dữ liệu.

### 9.3 Input Masking — biến thể so sánh, KHÔNG phải baseline

Input Masking là kỹ thuật duy nhất trong bài báo **không cần huấn luyện**: với mỗi người nói, nhân tín hiệu audio gốc với mặt nạ nhị phân theo RTTM (giữ đoạn của người đó, đưa phần còn lại về 0), rồi đưa vào ASR. Bài báo báo cáo kỹ thuật này một mình đã cải thiện đáng kể so với Whisper chạy thô trên audio nhiều người nói.

**Quy tắc bắt buộc:** thí nghiệm RQ2 (§8.6) chạy với `masking="none"`. Bật masking sẽ *làm giảm chính hiện tượng lan truyền lỗi mà RQ2 đang đo*, phá hỏng thí nghiệm.

Sau khi có đủ bảng kết quả 9 điều kiện, chạy thêm biến thể `masking="input_masking"` và báo cáo riêng:

| Cấu hình | cpWER (overlap 0%) | cpWER (overlap 15%) | cpWER (overlap 30%) |
| :---- | :---- | :---- | :---- |
| Cascaded thường |  |  |  |
| Cascaded \+ Input Masking |  |  |  |

Câu hỏi phụ: kỹ thuật này có thu hẹp khoảng cách `cpWER_cascaded − cpWER_oracle` không, và có hiệu quả hơn khi overlap cao không?

---

## 10\. CẤU TRÚC MÃ NGUỒN

cse457-meeting-asr/

├── README.md

├── requirements.txt

├── configs/

│   ├── default.yaml

│   ├── pyannote.yaml

│   ├── ecapa.yaml

│   └── confidence.yaml

├── src/                          \# pipeline lõi — KHÔNG import từ api/ hay web/

│   ├── \_\_init\_\_.py

│   ├── types.py                  \# Segment, Utterance, Turn, MeetingMinutes, \*Signals

│   ├── preprocess.py             \# M1

│   ├── diarization/

│   │   ├── base.py               \# Protocol

│   │   ├── pyannote\_backend.py   \# M2-A

│   │   └── ecapa\_backend.py      \# M2-B

│   ├── asr.py                    \# M3

│   ├── masking.py                \# Input Masking (§9.3)

│   ├── postprocess.py            \# M4

│   ├── confidence.py             \# M5 ⭐

│   ├── llm.py                    \# M6

│   ├── pipeline.py               \# ghép M1→M6

│   ├── cli.py                    \# chạy pipeline không cần web

│   └── io\_utils.py               \# đọc/ghi RTTM, JSON

├── data\_gen/

│   ├── simulate\_meeting.py

│   ├── add\_noise.py              \# MUSAN \+ RIR

│   └── validate\_dataset.py       \# 5 kiểm tra ở §7.4

├── evaluation/

│   ├── der.py

│   ├── wer.py

│   ├── cpwer.py

│   ├── turn\_wer.py               \# §8.4 — nhãn is\_bad

│   ├── flagging.py               \# §8.7 — P/R/F1, risk-coverage

│   └── run\_experiments.py        \# chạy toàn bộ ma trận

├── api/                          \# M7 backend

│   ├── main.py                   \# FastAPI

│   ├── jobs.py                   \# quản lý tác vụ nền

│   └── schemas.py                \# Pydantic

├── web/                          \# M7 frontend — Next.js

│   ├── app/

│   ├── components/

│   │   ├── TranscriptView.tsx

│   │   ├── FlaggedTurn.tsx       \# highlight \+ tooltip lý do

│   │   └── Timeline.tsx

│   └── lib/api.ts

├── tests/

│   ├── test\_io.py

│   ├── test\_simulate.py

│   ├── test\_metrics.py

│   └── test\_confidence.py

├── notebooks/

│   └── analysis.ipynb            \# vẽ biểu đồ cho báo cáo

├── data/                         \# .gitignore

│   ├── raw/  simulated/  real/

└── results/

    ├── experiments.csv

    └── figures/

---

## 11\. CẤU HÌNH

`configs/default.yaml`

seed: 42

preprocess:

  target\_sr: 16000

  normalize: true

  denoise: false

diarization:

  backend: pyannote            \# pyannote | ecapa

  min\_speakers: null

  max\_speakers: 6

  min\_segment\_duration: 0.3

  ecapa:

    vad\_threshold: 0.5

    window\_size: 1.5

    hop\_size: 0.75

    cluster\_threshold: 0.7

asr:

  model\_name: vinai/PhoWhisper-medium

  language: vi

  batch\_size: 8

  max\_segment\_sec: 28.0

  boundary\_pad: 0.1

  temperature: 0.0

  masking: none                \# none | input\_masking  (§9.3)

postprocess:

  merge\_gap: 0.8

  remove\_fillers: false        \# PHẢI để false khi đo WER

confidence:                    \# M5

  variant: full                \# full | no\_diar | asr\_only | random

  threshold: null              \# null \= tự chọn theo target\_coverage trên tập dev

  target\_coverage: 0.20

  margin\_ref\_percentile: 90

  weights:

    w\_asr: 0.30

    w\_speech: 0.10

    w\_rep: 0.10

    w\_ovl: 0.25

    w\_spk: 0.15

    w\_dur: 0.10

llm:

  enabled: true

  model: claude-sonnet-4-6

evaluation:

  der\_collar: \[0.25, 0.0\]

  skip\_overlap: \[true, false\]

  turn\_wer\_threshold: \[0.20, 0.30, 0.50\]

paths:

  data\_dir: ./data

  results\_dir: ./results

  cache\_dir: ./.cache

---

## 12\. KIỂM THỬ VÀ TIÊU CHÍ NGHIỆM THU

### 12.1 Unit test bắt buộc

| Test | Kiểm tra |
| :---- | :---- |
| `test_rttm_roundtrip` | Ghi RTTM rồi đọc lại → giống hệt object ban đầu |
| `test_rttm_duration_not_end` | RTTM ghi đúng `duration`, không phải `end` |
| `test_simulate_overlap_ratio` | Overlap thực tế sai lệch \< 3% so với mục tiêu |
| `test_simulate_no_clipping` | Max amplitude \< 0.999 |
| `test_no_consecutive_same_speaker` | Không có 2 lượt liên tiếp cùng người |
| `test_wer_nfc_normalization` | "ế" dạng NFC và NFD cho WER \= 0 |
| `test_merge_turns` | Gộp đúng theo `merge_gap` |
| `test_cpwer_permutation` | Đổi tên speaker không làm thay đổi cpWER |
| `test_overlap_ratio_calc` | `overlap_ratio` đúng trên 5 ca dựng tay |
| `test_confidence_missing_signal` | Tín hiệu `None` được loại và chuẩn hóa lại trọng số, không thành 0 |
| `test_confidence_monotonic` | Giảm bất kỳ `cᵢ` nào thì `confidence` không tăng |
| `test_flag_reasons` | Tín hiệu yếu nào cũng sinh đúng lý do tương ứng |
| `test_input_masking_shape` | Audio sau mask cùng độ dài, ngoài vùng target đúng bằng 0 |

### 12.2 Sanity check (chạy tay)

| Kiểm tra | Cách làm | Tần suất |
| :---- | :---- | :---- |
| Nghe file sinh ra | Mở 5 file bất kỳ, nghe xem có giống hội thoại | Mỗi lần đổi tham số sinh dữ liệu |
| Đối chiếu RTTM bằng tai | Chọn 1 segment, tua đến đúng giây đó, nghe xem có đúng người | Tuần 2 và mỗi khi DER lạ |
| Vẽ waveform | Nhìn xem có clipping (đầu sóng phẳng) | Tuần 2 |
| Mốc neo AMI | Chạy pipeline trên file mẫu AMI, so DER với con số công bố | Tuần 4, và mỗi khi nghi ngờ |
| **Đọc 10 đoạn bị gắn cờ** | Tự đọc xem có đúng là đoạn sai không | Mỗi lần đổi trọng số M5 |

> Kiểm tra cuối cùng quan trọng không kém metric: nếu bản thân mình đọc đoạn bị gắn cờ mà thấy nó vẫn đúng, thì heuristic đang bắt nhầm dù F1 có đẹp.

### 12.3 Definition of Done cho từng module

| Module | Xong khi |
| :---- | :---- |
| M1 | 4 assertion ở §6-M1 pass trên 20 file khác nhau, kể cả file stereo và 44.1kHz |
| M2 | Backend A: DER trên file mẫu AMI trong ±5% con số công bố. Backend B: DER ≤ 15% trên điều kiện sạch/0% overlap; xuất được `cluster_margin`. RTTM đọc được bằng `pyannote.metrics` |
| M3 | WER trên VIVOS test (oracle segment) \< 25%; không lặp vô hạn trên 100 file; **mọi Utterance đều có `ASRSignals` khác rỗng** |
| M4 | Gộp turn đúng trên 10 ca test tay |
| M5 | Toàn bộ test ở §12.1 liên quan confidence pass; sinh được bảng ablation 4 dòng và đường risk–coverage |
| M6 | LLM trả JSON hợp lệ 9/10 lần |
| M7 | Upload → xem → sửa đoạn flag → xuất file, end-to-end trên 3 file; bản sửa phản ánh đúng trong file xuất |
| M8 | Sinh được bảng đầy đủ cho cả 3 thí nghiệm §8.5–8.7 |

---

## 13\. KHẢ NĂNG TÁI LẬP

### 13.1 Log thí nghiệm

Mọi lần chạy ghi một dòng vào `results/experiments.csv`:

| Cột | Ví dụ |
| :---- | :---- |
| `run_id` | `2026-09-15_143022` |
| `git_commit` | `a3f9c21` |
| `config_hash` | md5 của file config |
| `dataset` | `sim_ovl15_snr15_spk3` |
| `diar_backend` | `ecapa` |
| `masking` | `none` |
| `der_lenient` / `der_strict` | 0.183 / 0.312 |
| `miss` / `fa` / `confusion` | 0.09 / 0.04 / 0.05 |
| `wer` | 0.214 |
| `cpwer_oracle` / `cpwer_cascaded` | 0.241 / 0.386 |
| `conf_variant` | `full` |
| `conf_threshold` / `coverage` | 0.42 / 0.197 |
| `flag_precision` / `flag_recall` / `flag_f1` / `flag_auc` | 0.71 / 0.64 / 0.67 / 0.78 |
| `rtf` | 1.34 |
| `notes` | "thử w\_ovl=0.30" |

### 13.2 Cố định tính ngẫu nhiên

import random, numpy as np, torch

def set\_seed(seed: int \= 42):

    random.seed(seed)

    np.random.seed(seed)

    torch.manual\_seed(seed)

    torch.cuda.manual\_seed\_all(seed)

    torch.backends.cudnn.deterministic \= True

### 13.3 Cache kết quả trung gian

Đặt tên cache theo `{audio_id}_{module}_{config_hash}.pkl`. Nếu file tồn tại thì đọc lại thay vì chạy lại.

> Đặc biệt quan trọng với M5: tinh chỉnh trọng số nghĩa là chạy M5 hàng chục lần. Nếu M1–M4 đã cache thì mỗi lần thử chỉ mất vài giây thay vì vài chục phút.

### 13.4 Quy ước Git

Mã nguồn đẩy lên GitHub **từ lúc bắt đầu triển khai**, vì điểm được đánh giá theo lịch sử đóng góp.

- Commit theo module: `feat(M5): thêm chuẩn hóa tín hiệu cluster_margin`  
- Mỗi lần chạy thí nghiệm có kết quả đáng chú ý: commit kèm dòng tương ứng trong `experiments.csv`  
- Không commit `data/` và `.cache/`  
- Tag mốc: `v0.1-pipeline-chay-duoc`, `v0.2-du-lieu-mo-phong`, `v0.3-danh-gia-day-du`

---

## 14\. LỘ TRÌNH

| Tuần | Mục tiêu | Sản phẩm kiểm chứng được |
| :---- | :---- | :---- |
| 1 | Chốt đề tài, dựng repo, spec v2.0 | Repo có cấu trúc §10, spec này đã commit |
| 2 | M1 \+ M2-A (pyannote) | 4 assertion M1 pass; RTTM đầu tiên; nghe đối chiếu bằng tai |
| 3 | M3 (PhoWhisper) \+ thu tín hiệu ASR | WER trên VIVOS oracle \< 25% |
| 4 | Sinh dữ liệu mô phỏng \+ mốc neo AMI | 180 phiên \+ 5 kiểm tra §7.4 pass |
| 5 | M8: DER, WER, cpWER — thí nghiệm RQ1 | Bảng §8.5 điền đủ cho backend A |
| 6 | Thí nghiệm RQ2 (oracle vs cascaded) | Bảng §8.6 |
| 7 | M2-B (ECAPA backend) \+ `cluster_margin` | Bảng §8.5 điền nốt cho backend B |
| 8 | **M5 — confidence \+ gắn cờ** | 4 biến thể chạy được, có điểm số |
| 9 | **Thí nghiệm RQ3 \+ tinh chỉnh trọng số** | Bảng ablation §8.7 \+ đường risk–coverage |
| 10 | M4 \+ M6 (LLM) \+ tự thu 5–10 cuộc | Biên bản hoàn chỉnh cho 1 cuộc họp thật |
| 11 | M7 — web (FastAPI \+ Next.js) | Demo end-to-end |
| 12 | Input Masking (§9.3) \+ viết báo cáo | Bảng so sánh \+ bản thảo báo cáo |

**Nếu bị chậm:** phần được phép cắt theo thứ tự — Input Masking (tuần 12\) → bộ phụ 60 phiên → FR-13/14/15 → giảm tập tự thu xuống 5 cuộc. **Không được cắt M5 hay M7**, vì đó là cam kết trong tên đề tài và mô tả đã đăng ký.

---

## PHỤ LỤC A — NHẬT KÝ QUYẾT ĐỊNH THIẾT KẾ

| Quyết định | Lý do | Ngày |
| :---- | :---- | :---- |
| Dùng cascaded thay vì end-to-end | Model end-to-end cho tiếng Việt chưa có sẵn; cascaded cho phép đo lan truyền lỗi — chính là RQ2 |  |
| Đánh giá chính trên dữ liệu mô phỏng | Không có benchmark diarization tiếng Việt công khai; mô phỏng cho ground truth chính xác miễn phí |  |
| Chỉ dùng VIVOS test split | Tránh nhiễm dữ liệu huấn luyện của PhoWhisper |  |
| Báo cáo DER cả 2 chế độ collar | Trung thực về khoảng cách giữa con số "đẹp" và thực tế |  |
| `remove_fillers: false` mặc định | Lọc từ đệm làm WER không so sánh được với công bố khác |  |
| **Nâng confidence flagging thành module M5 riêng** | Là nội dung trong tên đề tài đã đăng ký; đồng thời là phần đóng góp riêng duy nhất, cần metric và ablation đàng hoàng | 09/09/2026 |
| **Tín hiệu tin cậy thu tại M2/M3, tổng hợp tại M5** | Cho phép chạy lại M5 với trọng số khác mà không chạy lại ASR | 09/09/2026 |
| **ECAPA backend là bắt buộc, không tùy chọn** | Là pipeline đã đăng ký; và là nguồn duy nhất của `cluster_margin` cho ablation RQ3 | 09/09/2026 |
| **Web: Next.js \+ FastAPI thay Streamlit** | Mô tả đăng ký ghi rõ "xây dựng website"; đồng thời dùng được cho portfolio | 09/09/2026 |
| **Input Masking là biến thể so sánh, không phải baseline** | Bật mặc định sẽ làm giảm chính hiện tượng lan truyền lỗi mà RQ2 đo | 09/09/2026 |
| **Không cài đặt FDDT/QK-biasing** | Cần fine-tune trên dữ liệu hội thoại tiếng Việt có nhãn — không tồn tại; ngoài phạm vi §1.2 | 09/09/2026 |
| **Tách tập dev 30 phiên riêng cho M5** | Tinh chỉnh và báo cáo trên cùng tập là rò rỉ dữ liệu | 09/09/2026 |
| **Text ảo giác đặt rỗng thay vì xóa** | Xóa làm sai phép đo WER (biến insertion thành deletion) | 09/09/2026 |

> Ghi tiếp vào bảng này mỗi khi có quyết định thiết kế. Đây là tài liệu quý khi viết mục "Phương pháp" của báo cáo.

---

## PHỤ LỤC B — TRUY VẾT CAM KẾT ĐĂNG KÝ → ĐẶC TẢ

Bảng này để tự kiểm tra: mọi câu trong mô tả đã nộp cho giảng viên đều phải có chỗ trong spec.

| Câu trong bản đăng ký | Được hiện thực ở |
| :---- | :---- |
| "tự động phân tách người nói (Speaker Diarization)" | M2, FR-02 |
| "và phiên âm (ASR) cho các bản ghi cuộc họp tiếng Việt nhiều người tham gia" | M3, FR-03 |
| "biên bản họp gắn nhãn người nói kèm timestamp" | M4 \+ FR-06 |
| "đánh dấu các đoạn văn bản có độ tin cậy thấp để người dùng soát lại" | **M5**, FR-04/05/10, RQ3, §8.7 |
| "speaker embedding ECAPA-TDNN \+ clustering (nền tảng pyannote.audio)" | M2 Backend B (bắt buộc) \+ Backend A |
| "phiên âm bằng Whisper/PhoWhisper" | M3 — PhoWhisper mặc định, đối chiếu Whisper |
| "cơ chế đánh giá độ tin cậy (confidence heuristic) từ xác suất đầu ra của ASR" | M5 — tín hiệu `c_asr`, `c_speech`, `c_rep`; mở rộng thêm tín hiệu diarization |
| "đánh giá mức suy giảm hiệu năng (DER, WER, cpWER) dưới điều kiện chồng lấn giọng nói và nhiễu" | RQ1, §8.5, ma trận 9 điều kiện §7.2 |
| "Xây dựng website cho phép tải lên file ghi âm" | M7, FR-09 |
| "tự động trả về transcript gắn nhãn người nói" | M7 Transcript view |
| "highlight đoạn cần xem lại" | M7 Flag highlight, FR-10 |
| "kèm tóm tắt và danh sách việc cần làm do LLM trích xuất" | M6, FR-11 |
| Bài báo DiCoW | §9 |
| Gợi ý của giảng viên: 5–10 cuộc họp | §7.1 tập tự thu |

