import re

TABLE_MARK = '│'     # 칸 3개 이상 표의 셀 문단 접두(rules.text.table_mark와 동일해야 함)
IMG_RE = re.compile(r'\.(png|jpe?g|bmp|gif|tiff?)$', re.I)
