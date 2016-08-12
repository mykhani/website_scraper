#!/usr/bin/env python
# -*- coding: utf-8 -*-

from HTMLParser import HTMLParser
from collections import defaultdict
import requests, sys, re, json, MySQLdb, getpass

DATABASE = "ISHOPPINGPK"

class MYHTMLParser(HTMLParser):
	def __init__(self):
		# list of hyperlinks
		self._hyperlinks = []
		# list of hyperlink description
		self._descriptions = []
		self.menu_start = False
		self.capture_data = False
		self.data = ""
		# HTMLParser is an old style class so super() won't work
		# Call init method of parent class directly
		HTMLParser.__init__(self)

	# override some methods for desired functionality
	def handle_starttag(self, tag, attrs):
		# check for start of navingation menu
		if tag == 'nav':
			# return if attrs empty
			if not attrs:
				return

			pattern_menu = "cbp-hsmenu-wrapper"
			for attr in attrs:
				if pattern_menu in attr:
					self.menu_start = True

		# store all hyperlinks from menu
		if self.menu_start:
			if tag == 'a':
				# link is second tuple in attrs list
				for attr in attrs:
					ignore , link = attr
					match = re.match('http:', link)
					if not match:
						continue
					# check if link already stored to avoid duplication
					if link in self.hyperlinks:
						continue
					# description follows the http: link
					self.capture_data = True
					self.hyperlinks.append(link)

	def handle_endtag(self, tag):
		# check for data capture end
		if self.capture_data:
			if tag == 'a':
				self.capture_data = False
				self.descriptions.append(self.data)
				self.data = ""

		# check for menu end tag
		if self.menu_start:
			if tag == 'nav':
				self.menu_start = False

	def handle_data(self, data):
		if self.capture_data:
			data = data.strip()
			self.data += data

	@property
	def hyperlinks(self):
		"""Gets the hyperlinks encountered."""
		return self._hyperlinks

	@hyperlinks.setter
	def hyperlinks(self, link):
		self._hyperlinks.append(link)

	@property
	def descriptions(self):
		"""Gets the descriptions of hyperlinks."""
		return self._descriptions

	@descriptions.setter
	def descriptions(self, desc):
		"""Sets the descriptions value."""
		self._descriptions = desc

class ProductDatabase(object):
	def __init__(self, d, db, cursor):
		self._d = d
		self._cursor = cursor
		self._db = db

	def get_dictionary(self, d):
		for key, value in d.iteritems():
			if isinstance(value, dict):
				yield (key, value)
			else:
				yield (None, None)

	def create_mysql_database(self):

		self.create_categories_table()

		for class_name, category in self.get_dictionary(self._d):
			for subclass_name, subcategory in self.get_dictionary(category):
				subclass_url = subcategory.get('url', "")
				for type_name, type_dict in self.get_dictionary(subcategory):
					if type_dict:
						type_url = type_dict.get('url', {})
					else:
						type_url = ""
						type_name= ""

					self.add_to_categories(class_name, subclass_name, \
								subclass_url, type_name, \
								type_url)

					if not type_dict:
						break

	def create_categories_table(self):
		"""Create product catagories table in mysql database."""

		try :
			self._cursor.execute("DROP TABLE IF EXISTS CATEGORIES")
		except:
			print "Error deleting existing table"

		sql = """CREATE TABLE CATEGORIES (
			ID INT AUTO_INCREMENT,
			CLASS VARCHAR(100),
			SUBCLASS VARCHAR(100),
			SUBCLASSURL VARCHAR(200),
			TYPE VARCHAR(100),
			TYPEURL VARCHAR(200),
			PRIMARY KEY ( ID )
			)"""
		try :
			self._cursor.execute(sql)
		except:
			print "Error in executing SQL query"

	def add_to_categories(self, class_name, subclass_name, subclass_url, \
				type_name, type_url):

		sql = """INSERT INTO CATEGORIES (
			CLASS, SUBCLASS, SUBCLASSURL, TYPE, TYPEURL)
			VALUES ( \"%s\", \"%s\", \"%s\", \"%s\", \"%s\")""" \
			% (class_name, subclass_name, subclass_url, type_name, type_url)

		try:
			# Execute the SQL command
			self._cursor.execute(sql)
			# Commit your changes in the database
			self._db.commit()
		except:
			# Rollback in case there is any error
			self._db.rollback()

# get a connection to database
username = raw_input('Enter mysql username: ')
password = getpass.getpass('Enter mysql password: ')
# open connection to MySQL database server
try:
	db = MySQLdb.connect(host='localhost', user=username, passwd=password, db=DATABASE)
except:
	print "Failed to connect to MySQL database"
	sys.exit(1)

# create cursor object
cursor = db.cursor()
cursor.execute("SELECT VERSION()")

version =  cursor.fetchone()
print "Database version %s" % version

use_cache = True

if not use_cache:
	# create a session to use same TCP connection for all requests
	s = requests.Session()

	main_page = s.get('http://www.ishopping.pk')

	# check status code
	if main_page.status_code is not 200:
		print "Failed to load page"
		sys.exit(1)

	# instantiate html parser and feed it html data
	parser = MYHTMLParser()
	parser.feed(main_page.text)

	links = zip(parser.hyperlinks, parser.descriptions)

	# create a dictionary categorizing products
	product_catalog = defaultdict(defaultdict)

	for link in links:
		url, desc = link
		# copy url for later use
		urlcopy = url
		url = url.split('/')
		# ignore the base url
		url = url[3:]

		if len(url) == 1:
			key, extension = url[0].split('.')

			product_catalog[key] = {'all' : {'url' : urlcopy, 'description' : desc}}
			tmp = product_catalog[key]

		elif len(url) == 2:
			#tmp = tmp.append({'testing' : {'url' : urlcopy, 'description' : desc}})
			#tmp2 = tmp.append(tmp)
			key, extension = url[1].split('.')

			product_catalog[url[0]][key] = {'all' : {'url' : urlcopy, 'description' : desc}}
		elif len(url) == 3:
			# For example:
			# [u'electronics', u'mobile-phones-and-tablet-pc', u'tablet-pc-price-in-pakistan.html']
			key, extension = url[2].split('.')

			product_catalog[url[0]][url[1]][key] = {'url' : urlcopy, 'description' : desc}

	# dump json file data for debugging purposes
	with open('catalog.txt', 'w') as outfile:
		outfile.write(json.dumps(product_catalog, sort_keys=True, indent=4))
else:
	with open('catalog.txt', 'r') as infile:
		text = infile.read()
	product_catalog = json.loads(text)

# start populating database
database = ProductDatabase(product_catalog, db, cursor)

database.create_mysql_database()

# close the database connectioni
db.close()
