from collector.redevelop import biz_label, convert, detect, find_umd, read_rows, stage_no


def test_stage_text_maps_to_ordered_steps():
    assert stage_no("관리처분인가") == 4
    assert stage_no("사업시행계획인가") == 3
    assert stage_no("조합설립인가") == 2
    assert stage_no("추진위원회 승인") == 1
    assert stage_no("정비구역 지정") == 0
    assert stage_no("착공") == 6 and stage_no("준공인가") == 7   # '인가'가 있어도 준공이 이긴다
    assert stage_no("") is None


def test_columns_are_found_by_common_korean_names():
    cols = detect(["자치구", "정비구역명", "구역위치", "사업구분", "추진단계", "구역면적(㎡)", "계획세대수"], {})
    assert cols["zone"] == "정비구역명" and cols["stage"] == "추진단계" and cols["households"] == "계획세대수"
    assert cols["area"] == "구역면적(㎡)" and cols["sgg_name"] == "자치구"


def test_cp949_csv_is_read_and_converted(tmp_path):
    f = tmp_path / "서울_정비사업_20211227.csv"
    f.write_bytes(("자치구,정비구역명,구역위치,사업구분,추진단계,구역면적(㎡),계획세대수\n"
                   "마포구,아현2구역,마포구 아현동 699 일대,재개발,관리처분인가,\"47,000\",\"1,419\"\n").encode("cp949"))
    rows = read_rows(f)
    zones = convert(rows, detect(list(rows[0]), {}), "서울", "테스트", "2021-12-27")
    z = zones[0]
    assert z["sgg"] == "11440" and z["umd"] == "아현동" and z["stage_no"] == 4
    assert z["area"] == 47000 and z["households"] == 1419 and z["biz"] == "재개발"


def test_dong_and_business_labels():
    assert find_umd("서울특별시 성북구 장위동 68-1 일대", "성북구") == "장위동"
    assert find_umd("종로구 종로2가 1", "종로구") == "종로2가"
    assert biz_label("공공재개발") == "공공재개발" and biz_label("모아타운 관리계획") == "모아타운"
