# company_master_v5_3 데이터 설명서

## 1. 데이터 목적

`company_master_v5_3.csv`는 Battery Triage Map MVP에서 배터리 등급 판정 결과를 바탕으로 재사용·재활용·지정폐기물 처리 후보 업체를 추천하기 위한 업체 마스터 데이터입니다.

이 데이터의 역할은 다음과 같습니다.

```text
배터리 데이터 입력
→ rule.py 위험 여부 판단
→ triage.py 등급 산정
→ matching.py가 company_master_v5_3.csv에서 조건에 맞는 업체 추천
```

즉, 이 파일은 실제 운영 계약 DB가 아니라 **공모전 MVP 시연 및 매칭 로직 검증용 업체 후보 DB**입니다.

---

## 2. 최종 파일

| 파일 | 설명 |
|---|---|
| `company_master_v5_3.csv` | 최종 업체 마스터 데이터 30개 |
| `company_master_v5_3_kolas_check.csv` | KOLAS·공식 안전성검사기관 반영 상태 확인용 |
| `company_master_v5_3_check.csv` | 데이터 구성 요약 |
| `company_master_v5_3_matching_test.csv` | 배터리 300건 매칭 테스트 결과 |
| `patch_company_master_v5_3_official_kolas.py` | v5.3 수정 재현 코드 |

---

## 3. 데이터 구성 요약

최종 업체 수는 **30개**입니다.

| 구분 | 개수 | 설명 |
|---|---:|---|
| `reuse` | 10 | 재사용·재제조·정밀진단 후보 |
| `recycle` | 15 | 폐이차전지·폐축전지·금속 회수·재활용 후보 |
| `designated_waste` | 5 | 위험 배터리 또는 지정폐기물 처리 후보 |

데이터 검증 상태 기준으로는 다음과 같습니다.

| 구분 | 개수 | 의미 |
|---|---:|---|
| `user_verified` | 20 | 사용자가 검증한 업체 목록을 기준으로 반영한 업체 |
| `synthetic_demo` | 10 | MVP 시연 안정성을 위해 새로 생성한 보강 업체 |

> 주의: `is_synthetic_company = True`인 업체는 실제 업체가 아니라 시연용 보강 업체입니다. 다만 화면 표시에서 어색하지 않도록 업체명에는 “가상”이라는 단어를 넣지 않았습니다.

---

## 4. 데이터 생성 과정

### 4.1 사용자 검증 업체 우선 반영

사용자가 검증한 `known_battery_company_lookup_review.xlsx`를 기준으로 업체를 정리했습니다.

반영 원칙은 다음과 같습니다.

```text
1. 사용자 검증 업체를 우선 포함
2. TMC와 굿바이카는 제외
3. 검증된 업체가 30개보다 부족하므로, 부족분은 새로 생성한 시연용 업체로 보강
4. 최종 업체 수는 30개로 유지
```

### 4.2 제외 업체

아래 업체는 최종 데이터에서 제외했습니다.

| 업체 | 제외 이유 |
|---|---|
| TMC | 사용자 검증 결과 제외 대상 |
| 굿바이카 | 사용자 검증 결과 제외 대상 |

`company_master_v5_3.csv`에는 TMC와 굿바이카가 업체명 또는 설명 문구에 남지 않도록 정리했습니다.

### 4.3 부족 업체 10개 생성

검증 업체만으로는 `matching.py` 시연에 필요한 지역·등급·진단역량 조합을 충분히 커버하기 어렵기 때문에, 10개 업체는 MVP 시연용으로 생성했습니다.

생성 업체는 다음 원칙을 따릅니다.

```text
1. 업체명에는 “가상”이라는 단어를 표시하지 않음
2. 내부 컬럼에는 is_synthetic_company = True로 표시
3. source_dataset = SYNTHETIC_DEMO_COMPANY로 표시
4. verification_status = synthetic_demo로 표시
5. 실제 업체라고 오해하지 않도록 데이터 설명서와 내부 컬럼에 명시
```

---

## 5. 업체 유형별 의미

### 5.1 `reuse`

`reuse`는 재사용·재제조 또는 재사용 가능성 진단 경로를 의미합니다.

예시는 다음과 같습니다.

```text
Green / Yellow / Gray 배터리
→ 재사용 가능성 검토 또는 정밀진단 필요
→ reuse 업체 후보와 매칭
```

단, 모든 `reuse` 업체가 실제 재사용 처리업체라는 뜻은 아닙니다. 일부는 재사용 가능성 진단기관 또는 시연용 정밀진단센터입니다.

### 5.2 `recycle`

`recycle`은 폐이차전지, 폐축전지, 배터리 스크랩, 금속 회수, 원료 재생 등 재활용 처리 후보를 의미합니다.

```text
Orange 배터리
→ 재활용 후보
→ recycle 업체와 매칭
```

### 5.3 `designated_waste`

`designated_waste`는 침수·누액·화재·팽창·충격 등 위험 조건이 있는 배터리가 향할 수 있는 지정폐기물 처리 경로를 의미합니다.

현재 `triage.py`는 Red 등급을 직접 만들지 않고, 위험 배터리는 `rule.py`에서 별도 분기하는 구조입니다.

---

## 6. KOLAS 및 공식 안전성검사기관 반영 방식

이번 v5.3의 핵심 수정은 KOLAS를 과장하지 않고, 다음 두 개념을 분리했다는 점입니다.

```text
KOLAS 공인기관 여부
재사용전지/전기용품 안전성검사기관 지정 여부
```

### 6.1 반영 원칙

KOLAS는 회사 전체 인증이 아니라 특정 사업장과 특정 인정범위에 대한 인정입니다. 따라서 단순히 KOLAS가 확인되었다고 해서 전기차 배터리 SOH 또는 성능검사가 가능하다고 보지 않았습니다.

반영 기준은 다음과 같습니다.

| 구분 | DB 반영 |
|---|---|
| 배터리 재사용 안전성검사기관으로 확인 | `official_reuse_battery_inspection = True` |
| KOLAS가 확인되었지만 배터리 성능범위가 불명확 | `kolas_status`에 범위 확인 필요 표시 |
| KOLAS가 비배터리 범위로 확인 | 배터리 진단역량에 직접 반영하지 않음 |
| KOLAS 또는 공식검사기관 미확인 | `kolas_status = unconfirmed` |
| 시연용 생성 정밀진단센터 | `synthetic_demo_not_real_kolas`로 표시 |

### 6.2 업체별 주요 반영

| 업체 | 반영 결과 | 설명 |
|---|---|---|
| `(주)피엠그로우` | `official_reuse_battery_inspection = True`, `diagnostic_capability = kolas` | KOLAS는 미확인, 전기용품 안전성검사기관 확인. matching.py 호환을 위해 kolas 레벨로 매핑 |
| `(주)시스피아` | `official_reuse_battery_inspection = True`, `kolas_verified = True`, `diagnostic_capability = kolas` | KOLAS 공인교정기관 확인, 배터리 성능시험 인정범위는 추가 확인 필요. 공식 안전성검사기관 확인 |
| 현대글로비스 | 현재 v5.3 DB에는 없음 | KOLAS는 포장시험센터 범위로 확인되어 배터리 진단역량으로는 미반영 |
| 고려아연 온산제련소 | 현재 v5.3 DB에는 없음 | KOLAS는 화학/금속 분석 성격으로 확인되어 배터리 성능진단용으로는 미반영 |
| 그 외 실제 업체 | `kolas_status = unconfirmed` | 공개 근거 기준 KOLAS 또는 공식검사기관 미확인 |
| 생성 정밀진단센터 5개 | `diagnostic_capability = kolas`, `kolas_verified = False` | 실제 KOLAS가 아니라 MVP 시연용 정밀진단 역량 라벨 |

### 6.3 진단역량 분포

| diagnostic_capability | 개수 | 의미 |
|---|---:|---|
| `kolas` | 7 | 공식 안전성검사기관 또는 시연용 정밀진단센터 |
| `basic` | 15 | 일반 처리·재활용 선별 가능 수준 |
| `none` | 8 | 공식 진단역량 미확인 또는 지정폐기물 처리 중심 |

`kolas` 7개 중 실제 공식 안전성검사기관 기반은 **2개**이고, 시연용 생성 정밀진단센터는 **5개**입니다.

---

## 7. 주요 컬럼 설명

| 컬럼 | 설명 |
|---|---|
| `company_id` | 업체 고유 ID |
| `company_name` | 업체명 |
| `address` | 주소 |
| `region` | 시도 단위 지역 |
| `latitude`, `longitude` | 지도 표시 및 거리 계산용 좌표 |
| `is_active` | 운영 상태. MVP에서는 정상 후보만 사용 |
| `accepted_chemistry` | 수용 가능한 화학계. 현재는 모든 업체 `NCM,LFP` |
| `accepted_grade` | 수용 가능한 배터리 등급 |
| `diagnostic_capability` | `matching.py`에서 사용하는 진단역량. `none/basic/kolas` 중 하나 |
| `process_type` | 업체 유형. `reuse/recycle/designated_waste` |
| `monthly_capacity_count` | 월 처리 가능 수량. MVP용 추정값 |
| `license_type` | 업체 성격 또는 허가/역할 설명 |
| `source_dataset` | 데이터 출처 |
| `verification_status` | `user_verified` 또는 `synthetic_demo` |
| `is_synthetic_company` | 실제 검증 업체인지, 시연용 생성 업체인지 구분 |
| `official_reuse_battery_inspection` | 재사용전지/전기용품 안전성검사기관 확인 여부 |
| `kolas_verified` | KOLAS 확인 여부 |
| `kolas_status` | KOLAS 인정범위 해석 상태 |
| `kolas_accreditation_no` | KOLAS 인정번호가 확인된 경우 기록 |
| `kolas_scope_type` | KOLAS 인정범위 성격 |
| `kolas_battery_scope_verified` | 배터리 성능/SOH 인정범위 확인 여부 |
| `battery_diagnostic_scope_verified` | 배터리 진단 목적 인정 여부 |
| `diagnostic_capability_detail` | 진단역량 세부 설명 |
| `diagnostic_update_note` | KOLAS/공식검사기관 반영 사유 |

---

## 8. 실제 데이터와 합성 데이터 구분

이 데이터에서 “합성”은 두 가지 의미로 나뉩니다.

### 8.1 실제 업체지만 라벨이 합성된 경우

사용자 검증 업체는 실제 업체 후보입니다. 그러나 다음 값은 공개 데이터에서 바로 확인하기 어렵기 때문에 MVP용으로 라벨링했습니다.

```text
accepted_grade
accepted_chemistry
monthly_capacity_count
일부 diagnostic_capability
```

따라서 실제 업체라도 `is_synthetic_label = True`일 수 있습니다. 이것은 업체 자체가 가상이라는 뜻이 아니라, **매칭에 필요한 일부 컬럼을 MVP용 규칙으로 만들었다는 뜻**입니다.

### 8.2 업체 자체가 시연용으로 생성된 경우

`is_synthetic_company = True`인 10개 업체는 실제 업체가 아닙니다. 매칭 시연 안정성을 위해 만든 보강 업체입니다.

생성 업체 목록은 다음과 같습니다.


| 업체명 | 유형 | 지역 | 진단역량 |
|---|---|---|---|
| LFP재사용실증센터_충남 | reuse | 충남 | kolas |
| 배터리리유즈진단센터_경기 | reuse | 경기 | kolas |
| 배터리팩재제조센터_전남 | reuse | 전남 | kolas |
| 전기차배터리검사센터_부산 | reuse | 부산 | kolas |
| 폐배터리안전진단센터_인천 | reuse | 인천 | kolas |
| LFP재활용센터_경북 | recycle | 경북 | basic |
| NCM금속회수센터_충북 | recycle | 충북 | basic |
| 배터리스크랩재생센터_울산 | recycle | 울산 | basic |
| 전기차폐배터리전처리센터_전북 | recycle | 전북 | basic |
| 폐이차전지재활용센터_경기 | recycle | 경기 | basic |


---

## 9. 매칭 테스트 결과

`battery_cases_demo_lfp_v2.csv` 300건을 기준으로 `company_master_v5_3.csv`와 매칭 테스트를 수행했습니다.

전체 결과는 다음과 같습니다.

| match_status | 건수 |
|---|---:|
| matched | 300 |
| no_match | 0 |

등급별 결과는 다음과 같습니다.

| 등급 | matched |
|---|---:|
| Green | 77 |
| Yellow | 103 |
| Orange | 75 |
| Gray | 45 |

화학계별 결과는 다음과 같습니다.

| 화학계 | matched |
|---|---:|
| NCM | 228 |
| LFP | 25 |
| UNKNOWN | 47 |


모든 배터리 케이스에서 최소 1개 이상의 업체가 추천되었으므로, MVP 시연 기준으로는 매칭 안정성이 확보되었습니다.

---

## 10. 사용 방법

`matching.py`에서 사용할 때는 `company_master_v5_3.csv`를 업체 마스터로 읽으면 됩니다.

```python
import pandas as pd

companies = pd.read_csv("data/processed/company_master_v5_3.csv")
```

배터리 데이터는 다음 파일을 함께 사용합니다.

```text
battery_cases_demo_lfp_v2.csv
```

검증용으로는 다음 파일을 참고합니다.

```text
company_master_v5_3_matching_test.csv
company_master_v5_3_kolas_check.csv
company_master_v5_3_check.csv
```

---

## 11. 한계와 주의사항

### 11.1 실제 운영용 DB는 아님

이 데이터는 공모전 MVP 시연용입니다. 실제 운영에서는 업체별 계약 가능 여부, 실제 처리 가능 물량, 실제 수용 화학계, 허가 범위, 영업 상태를 다시 확인해야 합니다.

### 11.2 KOLAS는 인정범위 확인이 중요함

KOLAS는 특정 사업장과 특정 인정범위에 대한 인정입니다. 따라서 `kolas_verified = True`라고 하더라도 배터리 성능검사 또는 SOH 진단까지 가능하다고 단정하면 안 됩니다.

### 11.3 생성 업체는 화면 표시용 이름만 자연스럽게 처리함

생성 업체는 화면에서 “가상”이라는 단어가 보이지 않도록 업체명을 정리했습니다. 그러나 내부 컬럼에는 다음 값으로 명확히 구분됩니다.

```text
is_synthetic_company = True
verification_status = synthetic_demo
source_dataset = SYNTHETIC_DEMO_COMPANY
```

### 11.4 diagnostic_capability는 matching.py 호환용 값임

현재 `matching.py`는 `none/basic/kolas` 세 단계만 인식합니다. 그래서 피엠그로우와 시스피아처럼 공식 안전성검사기관 성격의 업체도 코드 호환을 위해 `diagnostic_capability = kolas`로 매핑했습니다.

정확한 의미는 `diagnostic_capability_detail`, `official_reuse_battery_inspection`, `kolas_status` 컬럼을 함께 봐야 합니다.

---

## 12. 발표용 권장 표현

아래 문장으로 설명하는 것이 가장 안전합니다.

```text
처리업체 데이터는 사용자 검증 업체 20개와 MVP 시연용 보강 업체 10개로 구성했다.
업체 유형은 재사용·재활용·지정폐기물 처리 경로로 나누었고, matching.py가 등급·화학계·거리·진단역량을 기준으로 1~3순위 업체를 추천할 수 있도록 구성했다.
KOLAS는 회사 전체 인증이 아니라 특정 인정범위에 대한 제도이므로, 본 데이터에서는 KOLAS 여부와 재사용전지 안전성검사기관 지정 여부를 분리해 관리했다.
피엠그로우와 시스피아는 공식 안전성검사기관으로 반영했으며, 시스피아의 KOLAS는 공인교정기관 범위로 확인되어 배터리 성능시험 인정범위는 추가 확인 대상으로 표시했다.
생성 업체는 실제 업체가 아닌 MVP 매칭 안정성 확보용 보강 데이터이며, 내부 컬럼으로 명확히 구분했다.
```

---

## 13. 최종 판단

`company_master_v5_3.csv`는 다음 목적에는 적합합니다.

```text
공모전 MVP 시연
Streamlit 지도 표시
배터리 등급별 업체 추천 시연
NCM/LFP/UNKNOWN 화학계 분기 시연
KOLAS/공식검사기관을 과장하지 않는 데이터 설명
```

다만 실제 운영 단계에서는 다음 검증이 추가로 필요합니다.

```text
업체별 허가증 확인
실제 폐배터리 수용 가능 여부 확인
NCM/LFP 화학계 수용 여부 확인
월 처리 가능 수량 확인
KOLAS 인정범위 원문 확인
재사용전지 안전성검사기관 최신 지정현황 확인
```
