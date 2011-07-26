#!/bin/sh
# Talk to cobbler,
# grab templates

server=`kenv -q boot.nfsroot.server`

mac=`kenv -q boot.netif.hwaddr`
ip=`kenv -q boot.netif.ip`
nm=`kenv -q boot.netif.netmask`
gw=`kenv -q boot.netif.gateway`
name=`kenv -q dhcp.host-name`
route=`kenv -q dhcp.routers`

# Determine if a given network interface has link
# XXX: some drivers only report link if the interface is UP
netif_up()
{
	local status

	status=`ifconfig $1 | sed -ne '/status:/p'`
	case $status in
		*active*)
			return 0
			;;
	esac
	return 1
}

# Returns true if a given network interface has the specified MAC address.
macmatch()
{
	local addr

	addr=`ifconfig $1 | sed -ne '/	ether /{s///;p;}'`
	[ "$addr" = "$2" ]
	return $?
}

for ifn in `ifconfig -l`; do
	case $ifn in
		*)
			if macmatch $ifn $mac; then
				iface=$ifn
			fi
			;;
	esac
done

# Bring up the interface.  Will confuse sysinstall, so we'll bring it
# back down after we fetch templates.
# Kinda assuming we're on the same subnet as the server, otherwise won't
# work.
ifconfig "$iface" "$ip" netmask "$nm"
route add default "$gw"

# If I don't have a name, then I have to get it...
if [ -z "$name" ]; then
	name=$(sed "s/MAC/${mac}/" <<EOT | nc $server 80 		\
		| sed -n 's/^.value..string.\([^<]*\)..string...value.$/\1/p'
POST /cobbler_api HTTP/1.0
Host: 127.0.0.1:80
User-Agent: Hand Rolled/1.0
Content-Type: text/xml
Content-Length: 250

<?xml version='1.0'?>
<methodCall>
<methodName>find_system</methodName>
<params>
<param>
<value><struct>
<member>
<name>mac_address</name>
<value><string>MAC</string></value>
</member>
</struct></value>
</param>
</params>
</methodCall>
EOT
	)
fi
# use Fetch to get my answer file from my cobbler server
# use awk to pull out different sections using "% /path/to/file" syntax.
fetch -qo - "http://$server/cblr/svc/op/ks/system/$name" |
	awk '/^% /{f=$2} /^[^%]/ && f{print > f}'

route del default
ifconfig $iface down

# Do some var substitution in cobbler.cfg
sed "s/IFACE/${iface}/g
     s/ROUTE/${route}/g
     s/IP/${ip}/g
     s/NM/${nm}/g" /stand/cobbler.cfg.tmpl > /stand/cobbler.cfg

