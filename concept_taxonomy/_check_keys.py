"""Check key encoding for backslashes."""
import sys
sys.path.insert(0, r'C:\Users\user\Desktop\fin ai\族群統計網頁')
from concept_groups import CONCEPT_GROUPS

keys = list(CONCEPT_GROUPS.keys())
print('Total keys:', len(keys))

slash_chr = chr(92)  # backslash
fwd_slash = chr(47)  # forward slash

for k in keys:
    if slash_chr in k or fwd_slash in k:
        print(repr(k))
