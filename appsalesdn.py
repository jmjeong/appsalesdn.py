#!/usr/bin/python
#
# appsalesdn.py
#
# iTune Connect Sales Reports Downloader(Dailys, Weekly, and Monthly reports)
# Copyright 2009 Jaemok Jeong(jmjeong@gmail.com)
#
# Version 1.1
#
# ChangeLog
#
# + fixes latest iTunes Connect changes
#
# Changes from appdailysales.py(Copyright 2008 Kirby Turner)
#   - Download all available reports including weekly and monthly report.
#   - Local cache : if downloaded file exists already, it will not try to download it.
#   - For the robustness, it relies heavily on BeautifulSoup module
#        Without BeautifulSoup module, it does not work.         
#   - Available report URL is gathered from dynamic html page.
#
# Original Notice:
#    This code is based on appdailysales.py
#    Copyright 2008 Kirby Turner
#    latest version and additional information available at:
#        http://appdailysales.googlecode.com/
#    
# This script will download available sales reports from
# the iTunes Connect web site.	The downloaded file is stored
# in the same directory containing the script file.	 Note: if
# the download file already exists then it won't download the file.
#
# This program relies on BeautifulSoup module to parse HTML data.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

# -- Change the following to match your credentials --
# -- or use the command line options.				--
appleId = 'Your Apple ID'
password = 'Your Password'
outputDirectory = '.'
unzipFile = True
verbose = False

# -- Site global Variable -- 
urlBase = 'https://itts.apple.com%s'
dailySalesPrefix = "S_D_"
weeklySalesPrefix = "S_W_"
monthlySalesPrefix = "S_M_"

# ----------------------------------------------------
import urllib
import urllib2
import cookielib
import datetime
import re
import getopt
import sys
import os
import gzip
import StringIO
import traceback

try:
	import BeautifulSoup
except ImportError:
	BeautifulSoup = None
	raise Exception, "BeautifulSoup module is required"

# The class ReportOptions defines a structure for passing
# report options to the download routine. The expected
# data attributes are:
#	appleId
#	password
#	outputDirectory
#	verbose
# Note that the class attributes will default to the global
# variable value equivalent.
class ReportOptions:
	def __getattr__(self, attrname):
		if attrname == 'appleId':
			return appleId
		elif attrname == 'password':
			return password
		elif attrname == 'outputDirectory':
			return outputDirectory
		elif attrname == 'verbose':
			return verbose
		elif attrname == 'unzipFile':
			return unzipFile
		else:
			raise AttributeError, attrname


def usage():
	print '''usage: %s [options]
Options and arguments:
-h	   : print this help message and exit (also --help)
-a uid : your apple id (also --appleId)
-p pwd : your password (also --password)
-o dir : directory where download file is stored, default is the current working directory (also --outputDirectory)
-u     : unzip download file, default is on (also --unzip)
-v     : verbose output, default is off (also --verbose)''' % sys.argv[0]

def processCmdArgs():
	global appleId
	global password
	global outputDirectory
	global unzipFile
	global verbose

	# Check for command line options. The command line options
	# override the globals set above if present.
	try: 
		opts, args = getopt.getopt(sys.argv[1:], 'ha:p:o:uv', ['help', 'appleId=', 'password=', 'outputDirectory=', 'unzip', 'verbose'])
	except getopt.GetoptError, err:
		#print help information and exit
		print str(err)	# will print something like "option -x not recongized"
		usage()
		return 2

	for o, a in opts:
		if o in ('-h', '--help'):
			usage()
			return 2
		elif o in ('-a', '--appleId'):
			appleId = a
		elif o in ('-p', '--password'):
			password = a
		elif o in ('-o', '--outputDirectory'):
			outputDirectory = a
		elif o in ('-v', '--verbose'):
			verbose = True
		elif o in ('-u', '--unzip'):
			unzipFile = True
		else:
			assert False, 'unhandled option'

# There is an issue with Python 2.5 where it assumes the 'version'
# cookie value is always interger.	However, itunesconnect.apple.com
# returns this value as a string, i.e., "1" instead of 1.  Because
# of this we need a workaround that "fixes" the version field.
#
# More information at: http://bugs.python.org/issue3924
class MyCookieJar(cookielib.CookieJar):
	def _cookie_from_cookie_tuple(self, tup, request):
		name, value, standard, rest = tup
		version = standard.get('version', None)
		if version is not None:
			version = version.replace('"', '')
			standard["version"] = version
		return cookielib.CookieJar._cookie_from_cookie_tuple(self, tup, request)


def showCookies(cj):
	for index, cookie in enumerate(cj):
		print index, ' : ', cookie
	

def downloadSalesData(opener, html, options, filenamePrefix, periodValue):
	global urlBase
	# Ah...more fun.  We need to post the page with the form
	# fields collected so far.	This will give us the remaining
	# form fields needed to get the download file.

	# Set the list of report dates.
	reportDates = []
	
	soup = BeautifulSoup.BeautifulSoup( html )
	form = soup.find( 'form', attrs={'name': 'frmVendorPage' } )
	urlDownload = urlBase % form['action']
	select = soup.find( 'select', attrs={'id': 'dayorweekdropdown'} )
	fieldNameDayOrWeekDropdown = select['name']
	reportDates = [tag['value'] for tag in soup.find('select', attrs={'id': 'dayorweekdropdown'}).findAll('option')]

	# for sales data
	fieldNameReportType = soup.find( 'select', attrs={'id': 'selReportType'} )['name']
	fieldNameReportPeriod = soup.find( 'select', attrs={'id': 'selDateType'} )['name']
	fieldNameDayOrWeekSelection = soup.find( 'input', attrs={'name': 'hiddenDayOrWeekSelection'} )['name'] #This is kinda redundant
	fieldNameSubmitTypeName = soup.find( 'input', attrs={'name': 'hiddenSubmitTypeName'} )['name'] #This is kinda redund	
	if options.verbose == True:
		print 'reportDates: ', reportDates

	unavailableCount = 0
	filenames = []

	if options.outputDirectory == "": options.outputDirectory = "."
	dailyfiles = [file for file in os.listdir(options.outputDirectory) if file.startswith(filenamePrefix)]

	for downloadReportDate in reportDates:
		# And finally...we're ready to download sales report.
		# first check if the download file exists
		checkfile = downloadReportDate.replace('/','')
		checkfile = checkfile.replace('#', '-')
		checkfile = filenamePrefix +  checkfile + ".txt"
		if options.unzipFile == False:
			checkfile += ".gz"
		if checkfile in dailyfiles:
			if options.verbose:
				print 'skip the file: ', checkfile
			continue
		
		webFormSalesReportData = urllib.urlencode({fieldNameReportType:'Summary', fieldNameReportPeriod:periodValue, fieldNameDayOrWeekDropdown:downloadReportDate, fieldNameDayOrWeekSelection:periodValue, fieldNameSubmitTypeName:'Download'})
		urlHandle = opener.open(urlDownload, webFormSalesReportData)

		try:
			filebuffer = urlHandle.read()
			urlHandle.close()

			filename = os.path.join(options.outputDirectory, checkfile)

			if options.unzipFile == True:
			 	if options.verbose == True:
					print 'unzipping archive file: ', filename
				ioBuffer = StringIO.StringIO(filebuffer)
				gzipIO = gzip.GzipFile('rb', fileobj=ioBuffer)
                                filebuffer = gzipIO.read()

			if options.verbose == True:
				print 'saving download file:', filename

			downloadFile = open(filename, 'w')
			downloadFile.write(filebuffer)
			downloadFile.close()

			filenames.append( checkfile )
		except AttributeError:
			print '%s report is not available - try again later.' % downloadReportDate
			unavailableCount += 1

	if unavailableCount > 0:
		raise Exception, '%i report(s) not available - try again later' % unavailableCount

	return filenames
	
def downloadFile(options):
	global urlBase
	
	if options.verbose == True:
		print '-- begin script --'

	cj = MyCookieJar();
	opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))

	# Go to the iTunes Connect website and retrieve the
	# form action for logging into the site.
	urlWebsite = urlBase % '/cgi-bin/WebObjects/Piano.woa'
	urlHandle = opener.open(urlWebsite)
	html = urlHandle.read()

	if options.verbose == True:
		print 'using BeautifulSoap for HTML parsing'

	soup = BeautifulSoup.BeautifulSoup( html )
	form = soup.find( 'form', attrs={'method': 'post' } )
	try:
		urlActionLogin = urlBase % form['action']
	except TypeError:   
		raise Exception, "Check Login id and Password again"
        
	# match = re.search('"appleConnectForm" action="(.*)"', html)
	# urlActionLogin = urlBase % match.group(1)

	# Login to iTunes Connect web site and go to the sales 
	# report page, get the form action url and form fields.	 
	# Note the sales report page will actually load a blank 
	# page that redirects to the static URL. Best guess here 
	# is that the server is setting some session variables 
	# or something.

	webFormLoginData = urllib.urlencode({'theAccountName':options.appleId, 'theAccountPW':options.password, '1.Continue.x':'0', '1.Continue.y':'0'})
	urlHandle = opener.open(urlActionLogin, webFormLoginData)
	html = urlHandle.read()


	# Get the form field names needed to download the report.
	soup = BeautifulSoup.BeautifulSoup( html )
	form = soup.find( 'form', attrs={'name': 'frmVendorPage' } )

	try:
		urlDownload = urlBase % form['action']
	except TypeError:   # if the page dont contain <form name='frmVendorPage'...>, login information would be wrong
		raise Exception, "Check Login id and Password again"
	
	fieldNameReportType = soup.find( 'select', attrs={'id': 'selReportType'} )['name']
	fieldNameReportPeriod = soup.find( 'select', attrs={'id': 'selDateType'} )['name']
	fieldNameDayOrWeekSelection = soup.find( 'input', attrs={'name': 'hiddenDayOrWeekSelection'} )['name'] #This is kinda redundant
	fieldNameSubmitTypeName = soup.find( 'input', attrs={'name': 'hiddenSubmitTypeName'} )['name'] #This is kinda redundant, too

	savedFilenames = []
	
	# process sales data (daily)
	webFormSalesReportData = urllib.urlencode({fieldNameReportType:'Summary', fieldNameReportPeriod:'Daily', fieldNameDayOrWeekSelection:'Daily', fieldNameSubmitTypeName:'ShowDropDown'})
	
	urlHandle = opener.open(urlDownload, webFormSalesReportData)
	html = urlHandle.read()
	
	filenames = downloadSalesData(opener, html, options, dailySalesPrefix, 'Daily')     # process daily log file
	savedFilenames.extend(filenames)

	# process sales data (weekly)
	webFormSalesReportData = urllib.urlencode({fieldNameReportType:'Summary', fieldNameReportPeriod:'Weekly', fieldNameDayOrWeekSelection:'Weekly', fieldNameSubmitTypeName:'ShowDropDown'})
	
	urlHandle = opener.open(urlDownload, webFormSalesReportData)
	html = urlHandle.read()
	
	filenames = downloadSalesData(opener, html, options, weeklySalesPrefix, 'Weekly')     # process weekly log file
	savedFilenames.extend(filenames)

	# process sales data (monthly)
	webFormSalesReportData = urllib.urlencode({fieldNameReportType:'Summary', fieldNameReportPeriod:'Monthly Free', fieldNameDayOrWeekSelection:'Monthly Free', fieldNameSubmitTypeName:'ShowDropDown'})
	
	urlHandle = opener.open(urlDownload, webFormSalesReportData)
	html = urlHandle.read()

	filenames = downloadSalesData(opener, html, options, monthlySalesPrefix, 'Monthly Free')     # process monthly log file
	savedFilenames.extend(filenames)

	if options.verbose == True:
		print '-- end of script --'

	return savedFilenames


def main():
	if processCmdArgs() > 0:	# Will exit if usgae requested or invalid argument found.
		return 2
	  
	# Set report options.
	options = ReportOptions()
	options.appleId = appleId
	options.password = password
	options.outputDirectory = outputDirectory
	options.unzipFile = unzipFile
	options.verbose = verbose
	# Download the file.
	filenames = downloadFile(options)

	return 0

if __name__ == '__main__':
  sys.exit(main())
