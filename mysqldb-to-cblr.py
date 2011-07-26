#!/usr/bin/env python

# Jonathan Sabo  <jonathan.sabo@gmail.com>

import MySQLdb
import sys
import optparse
import socket
from xmlrpclib import *

# Parse command line options
usage="%prog [-u] username [-p] password [-s] database server [-d] database [-r] prune [-P] profile [-n] hostdb node [-m] cobbler master [-b] netboot enabled"

parser = optparse.OptionParser(usage, version="%prog 1.0")
parser.disable_interspersed_args()

parser.add_option('-u', '--user',     help='username',                             dest='user_name',   action='store')
parser.add_option('-p', '--pass',     help='password',                             dest='password',    action='store')
parser.add_option('-n', '--node',     help='hostdb node',                          dest='hostdb_node', action='store')
parser.add_option('-m', '--master',   help='cobbler master  (default: localhost)', dest='cblr_master', action='store',      default="localhost")
parser.add_option('-s', '--dbserver', help='database server (default: localhost)', dest='db_server',   action='store',      default="localhost")
parser.add_option('-d', '--database', help='database name   (default: hosts)',     dest='database',    action='store',      default="hosts")
parser.add_option('-r', '--prune',    help='prune object    (default: false)',     dest='prune',       action='store_true', default="false")
parser.add_option('-b', '--netboot',  help='netboot-enabled (default: false)',     dest='netboot',     action='store_true', default="false")
parser.add_option('-P', '--profile',  help='profile         (default: default)',   dest='profile',     action='store',      default="default")

try:
    (opts, args) = parser.parse_args()
except SystemExit:
    sys.exit(1)

# Check command line options
if opts.user_name is None:
    parser.error("You must provide a user name")
if opts.password is None:
    parser.error("You must provide a password")
if opts.hostdb_node is None:
    parser.error("You must provide a hostdb node")

# Standard XML-RPC proxy
conn = ServerProxy("http://%s/cobbler_api" % opts.cblr_master)

# Authenticate with cobbler (requires authn-testing to work)
try:
    token = conn.login("testing","testing")
except (socket.gaierror, ProtocolError), reason:
    print "Unable to connect to %s (%s) " % (opts.cblr_master, reason)
    sys.exit(1)

# Create connection object and cursor
try:
    db = MySQLdb.connect(host=opts.db_server, user=opts.user_name, passwd=opts.password, db=opts.database)
    c = db.cursor(MySQLdb.cursors.DictCursor)
except MySQLdb.Error, reason:
    print "Unable to connect to database (%s)" % reason[1]
    sys.exit(1)

# Get the node id
try:
    getmachine_id = "select id from machines where node='%s'" % opts.hostdb_node
    c.execute(getmachine_id)
    id_results = c.fetchall()
except MySQLdb.Error, reason:
    print "Unable to find host in hostdb (%s)" % reason[1]
    sys.exit(1)

# For each machine
for row in id_results:
    try:
        # Get the machines info from the id
        getmachine_sql = "select * FROM machines where id = '%s'" % (row['id'])
        c.execute(getmachine_sql)
        machine_results = c.fetchall()
    except MySQLdb.Error, reason:
        print "Unable to find host (%s)" % reason[1]
        sys.exit(1)
    try:
        # Get the machines associated interface information
        getmachine_int_sql = "select * from interfaces where owner = '%s'" % (row['id'])
        c.execute(getmachine_int_sql)
        int_results = c.fetchall()
    except MySQLdb.Error, reason:
        print "Unable to find hosts interfaces (%s)" % reason[1]
        sys.exit(1)

    # From hostdb info create cobbler objects
    for m in machine_results:

        for k,v in m.iteritems():
            if v is None:
                m[k] = "" 

        # Check for system and create it if it doesn't exist
        try:
            # Delete it before its created if prune is set
            if opts.prune == True:
                conn.remove_system_handle(m['node'], token)
            else:
                sys_id = conn.get_system_handle(m['node'], token)
        except Fault, reason:
            if reason.faultCode == 1:
                sys_id = conn.new_system(token)
                pass
            else:
                raise
                sys.exit(1)

        try:
            conn.modify_system(sys_id, "profile", opts.profile, token)
        except Fault, reason:
            print "Unable to find requested profile (%s)" % reason.faultString
            sys.exit(1)

        conn.modify_system(sys_id, "name", m['node'], token)
        conn.modify_system(sys_id, "hostname", m['node'], token)
        conn.modify_system(sys_id, "gateway", m['gw'], token)
        conn.modify_system(sys_id, "netboot_enabled", opts.netboot, token)

        for i in int_results:

            for k,v in i.iteritems():
                if v is None:
                    i[k] = ""

            conn.modify_system(sys_id, 'modify_interface', {
                   "macaddress-%s"   % i['interface'] : i['mac'],
                   "ipaddress-%s"    % i['interface'] : i['ip'],
                   "subnet-%s"       % i['interface'] : i['netmask'],
                   "dnsname-%s"      % i['interface'] : i['name'],
                   "static-%s"       % i['interface'] : True
                   }, token)
            
        conn.save_system(sys_id, token)
