# detect_website_cdn

Tool that determines what content delivery networks (CDNs) are used to host a webpage. The tool works by collecting the hostnames from the URLs of all objects embedded within the webpages HTML root object. Then, the tool compares the hostnames against a dictionary of known CDN hostnames found in the "cdns" file.

Output of the tool is included in the output directory.

You can help make the tool better by contributing CDN domain names to the "cdns" file.

Thanks!
