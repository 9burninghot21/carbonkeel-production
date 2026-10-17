"""DB-IP country lite CSV -> compact range tables for ghgcore/geo.py (IP geolocation by DB-IP, CC BY 4.0)."""
import csv
import gzip
import ipaddress
import json
import os
import sys
from array import array

src, out = sys.argv[1], sys.argv[2]
os.makedirs(out, exist_ok=True)
codes, idx = [], {}
v4s, v4c, v6s, v6c = array("I"), array("H"), array("Q"), array("H")
with gzip.open(src, "rt", encoding="utf-8", newline="") as f:
    for start, end, cc in csv.reader(f):
        cc = cc.strip().upper()
        if not (len(cc) == 2 and cc.isalpha()):
            continue
        if cc not in idx:
            idx[cc] = len(codes)
            codes.append(cc)
        ip = ipaddress.ip_address(start)
        if ip.version == 4:
            v4s.append(int(ip)); v4c.append(idx[cc])
        else:
            v6s.append(int(ip) >> 64); v6c.append(idx[cc])
for name, arr in (("v4s", v4s), ("v4c", v4c), ("v6s", v6s), ("v6c", v6c)):
    with open(os.path.join(out, name + ".bin"), "wb") as f:
        arr.tofile(f)
json.dump({"codes": codes, "source": os.path.basename(src), "licence": "IP geolocation by DB-IP (db-ip.com), CC BY 4.0",
           "itemsize": {"I": array("I").itemsize, "H": array("H").itemsize, "Q": array("Q").itemsize}},
          open(os.path.join(out, "meta.json"), "w"))
print(len(v4s), len(v6s), len(codes))
