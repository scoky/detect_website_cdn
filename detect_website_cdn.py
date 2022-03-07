#!/usr/bin/python3

# Class for storing data collected about a domain
class Domain:
    def __init__(self, domain):
        self.domain = domain

# Gathered from eye-balling the data
CDN_ASNS = {
    '13335' : 'Cloudflare',
    '20940' : 'Akamai',
    '16509' : 'Amazon',
    '54113' : 'Fastly',
    '14153' : 'Edgecast',
    '19551' : 'Incapsula'
}
CDN_DOMAINS = {
    'cloudfront.net.' : 'Amazon',
    'amazonaws.com.' : 'Amazon',
    'edgekey.net.' : 'Akamai',
    'akamaiedge.net.' : 'Akamai',
    'akamaitechnologies.com.' : 'Akamai',
    'akamaihd.net.' : 'Akamai',
    'cloudflare.com.' : 'Cloudflare',
    'fastly.net.' : 'Fastly',
    'edgecastcdn.net.' : 'Edgecast',
    'impervadns.net.' : 'Incapsula'
}

def analyze_data(datas):
    from collections import defaultdict
    cdn_to_domains = defaultdict(lambda: [])
    for data in datas:
        data.cdn = CDN_ASNS[data.remote_asn] if data.remote_asn in CDN_ASNS else None
        if data.cdn is None: # Couldn't find a CDN by ASN
            for cname in data.cnames: # Search by CNAME
                for domain, cdn in CDN_DOMAINS.items():
                    if cname.endswith(domain):
                        data.cdn = cdn
        if data.cdn is not None: # Found a CDN for this domain
            cdn_to_domains[data.cdn].append(data)

    print('1. CDN analysis')
    print('Rank CDNs by number of sites')
    for cdn,sites in reversed(sorted(cdn_to_domains.items(), key = lambda x: len(x[1]))):
        print(cdn, len(sites))

    print()
    print('Rank CDNs by average TTFB')
    avgs = {}
    for cdn,sites in cdn_to_domains.items():
        import numpy
        avgs[cdn] = numpy.mean([data.ttfb for data in sites])
    for cdn,avg in sorted(avgs.items(), key = lambda x: x[1]):
        print(cdn, avg)

    print()
    print('Rank CDNs by DNS resolution time')
    for cdn,sites in cdn_to_domains.items():
        import numpy
        avgs[cdn] = numpy.mean([data.dns_resolution for data in sites])
    for cdn,avg in sorted(avgs.items(), key = lambda x: x[1]):
        print(cdn, avg)

    print()
    print('Rank CDNs by TCP handshake time')
    for cdn,sites in cdn_to_domains.items():
        import numpy
        avgs[cdn] = numpy.mean([data.tcp_handshake - data.dns_resolution for data in sites])
    for cdn,avg in sorted(avgs.items(), key = lambda x: x[1]):
        print(cdn, avg)

    print()
    print('Rank CDNs by TLS handshake time')
    for cdn,sites in cdn_to_domains.items():
        import numpy
        avgs[cdn] = numpy.mean([data.tls_handshake - data.tcp_handshake for data in sites])
    for cdn,avg in sorted(avgs.items(), key = lambda x: x[1]):
        print(cdn, avg)

    print()
    print('Rank CDNs by total download time')
    for cdn,sites in cdn_to_domains.items():
        import numpy
        avgs[cdn] = numpy.mean([data.download for data in sites])
    for cdn,avg in sorted(avgs.items(), key = lambda x: x[1]):
        print(cdn, avg)

    print()
    print('2. ASN analysis')
    print('Rank ASNs by number of sites')
    asn_to_sites = defaultdict(lambda: [])
    for data in datas:
        asn_to_sites[data.remote_asn].append(data)
    for asn,sites in reversed(sorted(asn_to_sites.items(), key = lambda x: len(x[1]))):
        print(asn, len(sites))

def process_domain(domain):
    try:
        hostname = 'www.' + domain # append the default label for the webserver to the hostname
        domain = Domain(domain) # object to store data

        # use curl to download the index
        import pycurl
        curl = pycurl.Curl()
        curl.setopt(pycurl.URL, 'https://{0}/'.format(hostname))
        curl.setopt(pycurl.FOLLOWLOCATION, 1)
        curl.setopt(pycurl.WRITEFUNCTION, lambda x: None)
        curl.setopt(pycurl.CONNECTTIMEOUT, 30) # 30 second timeout on connect
        curl.setopt(pycurl.TIMEOUT, 60) # 1 minute timeout on download
        response = curl.perform()
        domain.dns_resolution = curl.getinfo(pycurl.NAMELOOKUP_TIME)
        domain.tcp_handshake = curl.getinfo(pycurl.CONNECT_TIME)
        domain.tls_handshake = curl.getinfo(pycurl.APPCONNECT_TIME)
        domain.ttfb = curl.getinfo(pycurl.STARTTRANSFER_TIME)
        domain.download = curl.getinfo(pycurl.TOTAL_TIME)
        domain.remote_ip = curl.getinfo(pycurl.PRIMARY_IP)
        curl.close()

        # Use Team Cymru to lookup the ASN for the remote IP based upon BGP route advertisements
        from cymruwhois import Client
        cymru = Client()
        response = cymru.lookup(domain.remote_ip)
        domain.remote_asn = response.asn
        domain.remote_owner = response.owner

        # use dnspython package to obtain all CNAMEs from the hostname.
        # many CDNs use CNAME records as a means to onboard traffic.
        domain.cnames = []
        import dns.resolver
        answer = dns.resolver.query(hostname, 'A', lifetime = 5.0)
        for rrset in answer.response.answer:
            for rr in rrset:
                if rr.rdtype == 5: # CNAME
                    domain.cnames.append(str(rr.target))

        return domain
    except Exception as e:
        # Yes, catch alls are bad but this is a quick and dirty script
        import sys
        print(e, file = sys.stderr)
        return None

if __name__ == "__main__":
    import argparse,sys
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,\
                                     description='Search through website hostnames for signs of CDNs')
    parser.add_argument('--alexa_list', default='top-1m.csv')
    parser.add_argument('--alexa_limit', type=int, default=500)
    parser.add_argument('--intermediate_file', type=str, default='data.json')
    parser.add_argument('--skip_fetch', type=str, default=None)
    args = parser.parse_args()

    datas = []
    if args.skip_fetch is None: # Short circuit so that we can repeat the analysis multiple times without re-fetching the data
        domains = set()
        import csv
        with open(args.alexa_list, newline='') as csvfile:
            for row in csv.reader(csvfile):
                if len(domains) > args.alexa_limit:
                    break
                domains.add(row[1]) # Second column is the hostname

        from multiprocessing import Pool
        pool = Pool(None)
        complete = 0
        # Pass domains to the child processes to be fetched
        for data in pool.imap(process_domain, domains):
            if data is not None:
                datas.append(data)
                complete += 1
                print(complete, 'complete')

        with open(args.intermediate_file, 'w') as jsonfile:
            import json
            json.dump([d.__dict__ for d in datas], jsonfile)
    else:
        with open(args.skip_fetch, 'r') as jsonfile:
            import json
            for data in json.load(jsonfile):
                domain = Domain(None)
                for k,v in data.items():
                    setattr(domain, k, v)
                datas.append(domain)

    analyze_data(datas)