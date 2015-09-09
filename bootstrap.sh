#!/usr/bin/env bash
# Bootstrap script for DICE Monitoring Core Componets
#
#Copyright 2015, Institute e-Austria, Timisoara, Romania
#    http://www.ieat.ro/
#Developers:
# * Gabriel Iuhasz, iuhasz.gabriel@info.uvt.ro
#
#Licensed under the Apache License, Version 2.0 (the "License");
#you may not use this file except in compliance with the License.
#You may obtain a copy of the License at:
#    http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


#get kibana4 and  install
#TODO Replace wget

echo "Installing kibana...."
cd ~/ 
wget https://download.elasticsearch.org/kibana/kibana/kibana-4.0.1-linux-x64.tar.gz
tar xvf kibana-4.0.1-linux-x64.tar.gz
mkdir -p /opt/kibana
cp -R ~/kibana-4.0.1-linux-x64/* /opt/kibana/
echo "Registering Kibana as a service ...."
cd /etc/init.d && sudo wget https://gist.githubusercontent.com/thisismitch/8b15ac909aed214ad04a/raw/bce61d85643c2dcdfbc2728c55a41dab444dca20/kibana4
chmod +x /etc/init.d/kibana4
update-rc.d kibana4 defaults 96 9

#Start kibana after install #TODO need better solution
service kibana4 start

# install Java 8
echo "Installing Oracle Java 1.8 ...."
apt-get install python-software-properties -y
echo oracle-java8-installer shared/accepted-oracle-license-v1-1 select true | sudo /usr/bin/debconf-set-selections
add-apt-repository ppa:webupd8team/java -y
apt-get update -y
apt-get install oracle-java8-installer -y
apt-get install ant -y


# TODO Replace wget command

#cd /tmp
#wget -q --no-check-certificate https://github.com/aglover/ubuntu-equip/raw/master/equip_java8.sh && bash equip_java8.sh

# install Elasticsearch 1.4.4
echo "Installing Elasticsearch ...."
cd /opt
wget https://download.elastic.co/elasticsearch/elasticsearch/elasticsearch-1.4.4.tar.gz
tar zxf elasticsearch-1.4.4.tar.gz
ln -sf elasticsearch-1.4.4 elasticsearch

#delete config file
rm -f /opt/elasticsearch/config/elastcisearch.yml
#ln -sf /vagrant/elasticsearch.yml /opt/elasticsearch/config/elasticsearch.yml

# install Marvel (posibly obsolete afther further testing)
echo "Installing Elasticsearch plugin marvel ....."
/opt/elasticsearch/bin/plugin -i elasticsearch/marvel/latest


# install Logstash
echo "Installing Logstash..."
cd /opt
wget https://download.elastic.co/logstash/logstash/logstash-1.5.4.tar.gz
tar zxf logstash-1.5.4.tar.gz
ln -sf logstash-1.5.4 logstash


echo "Generating certificates for Logstash ..."
HostIP=$(ifconfig eth1 2>/dev/null|awk '/inet addr:/ {print $2}'|sed 's/addr://') #need to change to eth1 for vagrant

sed -i "/# Extensions for a typical CA/ a\subjectAltName = IP:$HostIP" /etc/ssl/openssl.cnf

#generate certificates

openssl req -config /etc/ssl/openssl.cnf -x509 -days 3650 -batch -nodes -newkey rsa:2048 -keyout /opt/IeAT-DICE-Repository/src/keys/logstash-forwarder.key -out /opt/IeAT-DICE-Repository/src/keys/logstash-forwarder.crt

# fix permissions
echo "Setting permissions ...."
cd /opt
chown -R vagrant.vagrant logstash* elasticsearch*
chown -R vagrant.vagrant /opt

echo "Finishing touches ....."
mkdir -p /etc/logstash/conf.d


echo "Bootstrapping done!"
