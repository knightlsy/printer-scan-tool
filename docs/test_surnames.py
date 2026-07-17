import sys
sys.path.insert(0, r"C:/Users/EDY/WorkBuddy/2026-07-07-10-57-44/printer-scan-tool")
from scangate.services import surnames as s

print("单姓数量:", len(s.SINGLE_SURNAMES))
print("复姓数量:", len(s.COMPOUND_SURNAMES))

cases = [
    ("张三", True, "张"),
    (" 李四", True, "李"),
    ("欧阳娜", True, "欧阳"),
    ("司马光", True, "司马"),
    ("长孙无忌", True, "长孙"),
    ("端木", True, "端木"),
    ("李雷", True, "李"),
    ("王芳", True, "王"),
    ("阿依古丽·买买提", True, "阿"),
    ("欧东阳", True, "欧"),
    ("赵子龙", True, "赵"),
    ("上官婉儿", True, "上官"),
    ("小名", False, None),
    ("John", False, None),
    ("张三@", False, None),
    ("张3", False, None),
    ("王", False, None),
    ("", False, None),
    ("   ", False, None),
    ("慕容复", True, "慕容"),
    ("诸葛孔明", True, "诸葛"),
    ("第五名", True, "第五"),
    ("爨姓人", True, "爨"),
]

allok = True
for name, expect_ok, expect_sur in cases:
    r = s.check_realname(name)
    ok = r["ok"]
    sur = r.get("surname")
    flag = "OK" if ok == expect_ok else "FAIL"
    if ok != expect_ok:
        allok = False
    if ok and expect_sur and sur != expect_sur:
        allok = False
        flag = "FAIL(surname)"
    extra = "" if ok else "  err=" + r.get("error", "")
    print(f"  {name!r:20} -> ok={ok} sur={sur}  expect_ok={expect_ok} {flag}{extra}")

print("\n全部用例通过" if allok else "\n存在失败用例")
