"""CSV ingest 무업로드 (dry-run) 검증."""
from pathlib import Path
import tempfile
import textwrap

from scripts.ingest_csv import run as ingest_csv_run


def test_ingest_csv_dry_run(tmp_path: Path):
    csv = tmp_path / "tiny.csv"
    csv.write_text(textwrap.dedent("""\
        sku_id,brand,category,model_number,voltage_v,current_a,power_w,switching_freq_hz,certifications,datasheet_url
        t-abb-1,ABB,igbt-module,T-1,1200,300,,2000,KEPIC-EN:KEPIC,
        t-inf-1,Infineon,igbt-module,T-2,1700,500,,2000,,
    """), encoding="utf-8")

    out_dir = tmp_path / "out"
    rc = ingest_csv_run(csv, dry_run=True, out_dir=out_dir)
    assert rc == 0
    ttls = list(out_dir.glob("skus_*.ttl"))
    assert len(ttls) == 1
    text = ttls[0].read_text(encoding="utf-8")
    assert "cat:SKU" in text
    assert "exSku:t-abb-1" in text
    assert "KEPIC" in text


def test_ingest_csv_drops_invalid_row(tmp_path: Path):
    csv = tmp_path / "bad.csv"
    csv.write_text(textwrap.dedent("""\
        sku_id,brand,category,model_number,voltage_v,current_a,power_w,switching_freq_hz,certifications,datasheet_url
        good,ABB,igbt-module,G-1,1200,300,,,,
        bad,,igbt-module,B-1,1200,300,,,,
    """), encoding="utf-8")

    out_dir = tmp_path / "out"
    rc = ingest_csv_run(csv, dry_run=True, out_dir=out_dir)
    # 1건 valid, 1건 invalid → rc=1 (errors 있음)
    assert rc == 1
    err = (out_dir / "errors.log").read_text(encoding="utf-8")
    assert "bad" in err
