from pathlib import Path
from monitor.config import load_sites

def test_load_sites_reads_excel_compatible_csv(tmp_path: Path):
    csv_path = tmp_path / "sites.csv"
    csv_path.write_text(
        "\ufeffprovince,url,description,notes,dynamic\n"
        "上海市,https://example.gov.cn/a,测试,备注,false\n",
        encoding="utf-8",
    )
    sites = load_sites(csv_path)
    assert len(sites) == 1
    assert sites[0].province == "上海市"
    assert sites[0].dynamic is False
