#!/usr/bin/python

import os
import sys
import argparse
import signal
import requests
import socket
from multiprocessing import Pool
from HTMLParser import HTMLParser
from urlparse import urlparse

# Exception thrown when a timeout occurs
class TimeoutError(Exception):
    pass
# Helper class for throwing timeout exceptions
class Timeout:
    def __init__(self, seconds=10, error_message='Timeout'):
        self.seconds = seconds
        self.error_message = error_message
    def handle_timeout(self, signum, frame):
        raise TimeoutError(self.error_message)
    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)
    def __exit__(self, type, value, traceback):
        signal.alarm(0)
    
# State data per website
class Website(object):
    def __init__(self, hostname):
        self.root = hostname
        self.hostnames = set()
        self.hostnames.add(hostname)
        self.cdns = set()

    @classmethod
    def debug_headers(cls):
        return 'ROOT HOSTNAMES'
        
    def debug_output(self):
        return ' | '.join(map(str, (self.hostname, ','.join(self.hostnames))))
        
# Parse HTML looking for hostnames in embedded resources
class HostnameParser(HTMLParser):
    def hostname_list(self, hostnames):
        self.hostnames = hostnames

    def handle_starttag(self, tag, attrs):
        key = None
        if tag == 'img' or tag == 'script': # Pull sources URLs of images and scripts
            key = 'src'
        elif tag == 'link': # Pull HREF for links (i.e., css)
            key = 'href'
        
        if key:
            for attr,value in attrs: # Search attributes for src/href
                if attr == key:
                    hostname = urlparse(value).netloc
                    if hostname:
                        self.hostnames.add(hostname)
                    break            
        
def fetch_hostname(hostname):
    site = Website(hostname)
    try:
        with Timeout(seconds=20): # Give up after 20 seconds
            response = requests.get('http://'+hostname)  

        # Get the hostnames of embedded resources within the page
        parser = HostnameParser()
        parser.hostname_list(site.hostnames)
        parser.feed(response.content.decode(response.encoding))
        # Get canonical name for each hostname
        fqdn_hostnames = set()
        for host in site.hostnames:
            try:
                fqdn = socket.getfqdn(host)
                fqdn_hostnames.add(fqdn)
            except IOError: # Error in resolution, nothing to be done about it
                pass
        # Save all hostnames to the state object
        site.hostnames = site.hostnames.union(fqdn_hostnames)
    except Exception as e:
        sys.stderr.write('Error fetching website '+hostname+': '+str(e)+'\n')
    return site
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,\
                                     description='Search through website hostnames for signs of CDNs')
    parser.add_argument('-o', '--output', type=argparse.FileType('w'), default=sys.stdout, help='output file')
    parser.add_argument('-s', '--sites', type=argparse.FileType('r'), default=sys.stdin, help='one hostname per line')
    parser.add_argument('-c', '--cdns', type=argparse.FileType('r'), default=sys.stdin, help='database of known CDNs to domains, <cdn> <domain> per line')
    args = parser.parse_args()

    # Build the dictionary of CDNs from input file
    cdns = {}
    for line in args.cdns:
        cdn,domain = line.strip().split()
        cdns[domain] = cdn
    args.cdns.close()
    
    pool = Pool(None)
    index = 0
    # Pass sites to the child processes to be fetched
    for site in pool.imap(fetch_hostname, (line.strip() for line in args.sites)):
        # Compare hostnames in page to known hostnames for CDNs
        for hostname in site.hostnames:
            for domain,cdn in cdns.iteritems():
                if hostname.endswith(domain):
                    site.cdns.add(cdn)
                    break
        # Output website along with list of CDNs that it uses
        args.output.write("%s;%s\n" % (site.root, ','.join(site.cdns)))
        index += 1
        sys.stderr.write("%d complete\n" % index)        
