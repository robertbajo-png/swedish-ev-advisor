"""Capture public dealer candidates for review; this command cannot approve or publish them."""
import argparse
from pathlib import Path
from urllib.parse import urlsplit

from collect_release_sources import capture
from audit_catalog_sources import ROOT

DOMAINS={'www.volvocarretail.se','dinbil.se','www.vwgroup.se','lagerbilar.vwgroup.se','www.bilia.se','hedinautomotive.se','www.hoglundsbil.se'}


def candidate_url(url,brands):
    try:
        parsed=urlsplit(url)
        return (parsed.scheme=='https' and parsed.hostname in DOMAINS and not parsed.username and not parsed.password
            and parsed.port in (None,443) and not parsed.fragment)
    except ValueError:
        return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--brand',required=True,choices=['Volvo','Volkswagen','Audi','Skoda','Cupra','Mercedes-Benz'])
    parser.add_argument('--url',required=True)
    args=parser.parse_args()
    result=capture(args.url,{args.brand},ROOT/'data/local/release-data/dealer-candidates',url_policy=candidate_url)
    print({key:result.get(key) for key in ['status','http_status','content_hash','body_file','final_url']})
    print('Discovery only: authorization, exact vehicle identity, new condition and tax/price evidence still required. No database writes.')


if __name__=='__main__':main()
