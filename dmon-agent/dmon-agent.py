"""

Copyright 2015, Institute e-Austria, Timisoara, Romania
    http://www.ieat.ro/
Developers:
 * Gabriel Iuhasz, iuhasz.gabriel@info.uvt.ro

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at:
    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from flask import send_file
from flask import request, abort
from flask.ext.restplus import Resource, fields
import os
import jinja2
import sys
import subprocess
import platform
import logging
import shutil

from logging.handlers import RotatingFileHandler

from pyUtil import *
from app import *


# directory location
logDir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'log')
tmpDir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
pidDir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'pid')
collectdlog = '/var/log/collectd.log'
collectdpid = os.path.join(pidDir, 'collectd.pid')
lsflog = '/var/log/logstash-fowarder/logstash-fowarder.log'
lsferr = '/var/log/logstash-fowarder/logstash-fowarder.err'
collectdConf = '/etc/collectd/collectd.conf'
lsfConf = '/etc/logstash-forwarder.conf'
lsfList = os.path.join(tmpDir, 'logstashforwarder.list')
lsfGPG = os.path.join(tmpDir, 'GPG-KEY-elasticsearch')
certDir = '/opt/certs/'
certLoc = os.path.join(certDir, 'logstash-forwarder.crt')

# supported aux components
# auxList = ['collectd', 'lsf', 'jmx']


nodeRoles = api.model('query details Model', {
    'roles': fields.List(fields.String(required=False, default='hdfs',
                                       description='Roles assigned to this node!'))
})


collectdConfModel = api.model('configuration details Model for collectd', {
    'LogstashIP': fields.String(required=True, default='127.0.0.1', description='IP of the Logstash Server'),
    'UDPPort': fields.String(required=True, default='25680', description='Port of UDP plugin from Logstash Server'),
    'Interval': fields.String(required=False, default='15', description='Polling interval for all resources')
})

lsfConfModel = api.model('configuration details Model for LSF', {
    'LogstashIP': fields.String(required=True, default='127.0.0.1', description='IP of the Logstash Server'),
    'LumberjackPort': fields.String(required=True, default='5000', description='Logstash Lumberjack input port')
})

yarnProperties = api.model('Yarn properties configuration Model', {
    'Period': fields.String(required=True, default='10', description='Polling period for all Yarn/HDFS metrics')
})

sparkProperties = api.model('Spark properties configuration Model', {
    'LogstashIP': fields.String(required=True, default='109.231.121.210', description='Logstash IP (only Spark)'),
    'GraphitePort': fields.String(required=True, default='5002', description='Logstash Graphite input Port (only Spark)'),
    'Period': fields.String(required=True, default='5', description='Spark Polling Period')
})
# Instance of AuxComponent Class
aux = AuxComponent(lsfList, lsfGPG)


@agent.route('/v1/node')
class NodeInfo(Resource):
    def get(self):
        mType = platform.uname()
        response = jsonify({'System': mType[0],
                            'Node': mType[1],
                            'Release': mType[2],
                            'Version': mType[3],
                            'Machine': mType[4],
                            'Processor': mType[5]})
        response.status_code = 200
        return response


@agent.route('/v1/deploy')
class NodeDeploy(Resource):
    @api.expect(nodeRoles)
    def post(self):
        rolesList = request.json['roles']
        app.logger.info('[%s] : [INFO] Role list received: %s',
                        datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(rolesList))
        try:
            aComp = aux.install(rolesList)
        except Exception as inst:
            # print >> sys.stderr, type(inst)
            # print >> sys.stderr, inst.args
            app.logger.error('[%s] : [ERROR] Installing components based on roles with: %s and %s',
                             datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), type(inst), inst.args)
            response = jsonify({'Status': 'System Error',
                               'Message': 'Error while installing components'})
            response.status_code = 500
            return response
        response = jsonify({'Status': 'Done',
                            'Components': aComp})
        app.logger.info('[%s] : [INFO] Installed: %s',
                        datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(aComp))
        response.status_code = 201
        return response


@agent.route('/v1/collectd')
class NodeDeployCollectd(Resource):
    @api.expect(collectdConfModel)
    def post(self):
        collectdTemp = os.path.join(tmpDir, 'collectd.tmp')
        if not request.json:
            response = jsonify({'Status': 'Malformed request, json expected'})
            response.status_code = 400
            app.logger.warning('[%s] : [WARN] Malformed request, json expected', datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
            return response

        reqKeyList = ['LogstashIP', 'UDPPort', 'Interval']
        for k in request.json:
            app.logger.info('[%s] : [INFO] Key found %s', datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), k)
            if k not in reqKeyList:
                response = jsonify({'Status': 'Unrecognized key %s' %(k)})
                response.status_code = 400
                app.logger.warning('[%s] : [WARN] UNsuported key  %s', datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), k)
                return response
        if 'LogstashIP' not in request.json or 'UDPPort' not in request.json:
            response = jsonify({'Status': 'Missing key(s)'})
            response.status_code = 400
            app.logger.warning('[%s] : [WARN] Missing key(s)', datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
            return response
        if 'Interval' not in request.json:
            pollInterval = '10'
        else:
            pollInterval = request.json['Interval']

        settingsDict = {'logstash_server_ip': request.json['LogstashIP'],
                        'logstash_server_port': request.json['UDPPort'],
                        'collectd_pid_file': '/var/run/collectd.pid',
                        'poll_interval': pollInterval}
        aux.configureComponent(settingsDict, collectdTemp, collectdConf)
        aux.controll('collectd', 'restart')
        response = jsonify({'Status': 'Done',
                            'Message': 'Collectd Started'})
        app.logger.info('[%s] : [INFO] collectd started with: %s',
                        datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(settingsDict))
        response.status_code = 200
        return response


@agent.route('/v1/lsf')
class NodeDeployLSF(Resource):
    @api.expect(lsfConfModel)
    def post(self):
        lsfTemp = os.path.join(tmpDir, 'logstash-forwarder.tmp')
        if not request.json:
            response = jsonify({'Status': 'Malformed request, json expected'})
            response.status_code = 400
            app.logger.warning('[%s] : [WARN] Malformed request, json expected', datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
            return response
        reqKeyList = ['LogstashIP', 'LumberjackPort']
        for k in request.json:
            app.logger.info('[%s] : [INFO] Key found %s', datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), k)
            if k not in reqKeyList:
                response = jsonify({'Status': 'Unrecognized key %s' %(k)})
                response.status_code = 400
                app.logger.warning('[%s] : [WARN] UNsuported key  %s', datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), k)
                return response
        settingsDict = {'ESCoreIP': request.json['LogstashIP'],
                         'LSLumberPort': request.json['LumberjackPort']}
        app.logger.info('[%s] : [INFO] Logstash-Forwarder settings:  %s',
                        datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(settingsDict))
        if not os.path.isfile(certLoc):
            app.logger.warning('[%s] : [WARN] Logstash Server certificate not detected',
                        datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
            response = jsonify({'Status': 'Env Error',
                                'Message': 'LS Server certificate is missing'})
            response.status_code = 404
            return response
        aux.configureComponent(settingsDict, lsfTemp, lsfConf)
        aux.controll('logstash-forwarder', 'restart')
        response = jsonify({'Status': 'Done',
                            'Message': 'LSF Stated'})
        response.status_code = 200
        return response


@agent.route('/v1/jmx')
class NodeDeployJMX(Resource):
    def post(self):  # TODO:  implement or remove.
        return "JMX redeploy"


@agent.route('/v1/start')
class NodeMonitStartAll(Resource):
    def post(self):
        try:
            aux.controll('collectd', 'start')
        except Exception as inst:
            # print >> sys.stderr, type(inst)
            # print >> sys.stderr, inst.args
            app.logger.error('[%s] : [ERROR] While starting collectd with: %s and  %s',
                             datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), type(inst), inst.args)
            response = jsonify({'Status': type(inst),
                               'Message': inst.args})
            response.status_code = 500
            return response
        try:
            aux.controll('logstash-forwarder', 'start')
        except Exception as inst:
            # print >> sys.stderr, type(inst)
            # print >> sys.stderr, inst.args
            app.logger.error('[%s] : [ERROR] While logstash-forwarder collectd with: %s and  %s',
                             datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), type(inst), inst.args)
            response = jsonify({'Status': type(inst),
                               'Message': inst.args})
            response.status_code = 500
            return response
        response = jsonify({'Status': 'Started',
                            'Message': 'Auxiliary components started!'})
        response.status_code = 200
        return response


@agent.route('/v1/stop')
class NodeMonitStopAll(Resource):
    def post(self):
        try:
            aux.controll('collectd', 'stop')
        except Exception as inst:
            # print >> sys.stderr, type(inst)
            # print >> sys.stderr, inst.args
            app.logger.error('[%s] : [ERROR] While stopping collectd with: %s and  %s',
                             datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), type(inst), inst.args)
            response = jsonify({'Status': type(inst),
                               'Message': inst.args})
            response.status_code = 500
            return response
        try:
            aux.controll('logstash-forwarder', 'stop')
        except Exception as inst:
            # print >> sys.stderr, type(inst)
            # print >> sys.stderr, inst.args
            app.logger.error('[%s] : [ERROR] While stopping logstash-forwarder with: %s and  %s',
                             datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), type(inst), inst.args)
            response = jsonify({'Status': type(inst),
                               'Message': inst.args})
            response.status_code = 500
            return response
        response = jsonify({'Status': 'Stopped',
                            'Message': 'Auxiliary components stopped!'})
        response.status_code = 200
        return response


@agent.route('/v1/start/<auxComp>')
@api.doc(params={'auxComp': 'Can be collectd or lsf'})
class NodeMonitStartSelective(Resource):
    def post(self, auxComp):
        if not aux.check(auxComp):
            response = jsonify({'Status': 'Parameter error',
                                'Message': 'Unsupported Parameter' + auxComp})
            app.logger.warning('[%s] : [WARN] Unsuported parameter: %s',
                               datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(auxComp))
            response.status_code = 400
            return response

        try:
            aux.controll(auxComp, 'start')
        except Exception as inst:
            # print >> sys.stderr, type(inst)
            # print >> sys.stderr, inst.args
            response = jsonify({'Status': type(inst),
                               'Message': inst.args})
            app.logger.error('[%s] : [ERROR] starting collectd with:%s and %s',
                             datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), type(inst), inst.args)
            response.status_code = 500
            return response
        response = jsonify({'Status': 'Done',
                            'Message': 'Component ' + auxComp + ' started!'})
        response.status_code = 200
        return response


@agent.route('/v1/stop/<auxComp>')
@api.doc(params={'auxComp': 'Can be collectd or lsf'})
class NodeMonitStopSelective(Resource):
    def post(self, auxComp):
        if not aux.check(auxComp):
            response = jsonify({'Status': 'Parameter error',
                                'Message': 'Unsupported Parameter' + auxComp})
            app.logger.warning('[%s] : [WARN] Unsupported parameter: %s',
                               datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(auxComp))
            response.status_code = 400
            return response

        try:
            aux.controll(auxComp, 'stop')
        except Exception as inst:
            app.logger.error('[%s] : [ERROR] Error starting %s with : %s and %s',
                             datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(auxComp), type(inst), inst.args)
            response = jsonify({'Status': type(inst),
                               'Message': inst.args})
            response.status_code = 500
            return response
        response = jsonify({'Status': 'Done',
                            'Message': 'Component ' + auxComp + ' stopped!'})
        response.status_code = 200
        return response


@agent.route('/v1/log')
class NodeLog(Resource):
    def get(self):
        agentlog = os.path.join(logDir, 'dmon-agent.log')
        try:
            logFile1 = open(agentlog, 'r')
        except Exception as inst:
            app.logger.error('[%s] : [ERROR] Opening log with %s and %s',
                               datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), type(inst), inst.args)
            response = jsonify({'Status': 'File Error',
                                    'Message': 'Cannot open log file'})
            response.status_code = 500
            return response
        app.logger.info('[%s] : [INFO] Agent log file -> %s',
                        datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(agentlog))
        return send_file(logFile1, mimetype='text/plain', as_attachment=True)


@agent.route('/v1/log/component/<auxComp>')
@api.doc(params={'auxComp': 'Can be collectd or lsf'})
class NodeMonitLogs(Resource):
    def get(self, auxComp):
        if not aux.check(auxComp):
            response = jsonify({'Status': 'Parameter error',
                                'Message': 'Unsupported Parameter' + auxComp})
            app.logger.warning('[%s] : [WARN] Unsupported parameter: %s',
                               datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(auxComp))
            response.status_code = 400
            return response
        if auxComp == 'collectd':
            try:
                clog = open(collectdlog, 'w+')
            except Exception as inst:
                app.logger.error('[%s] : [ERROR] Opening collectd log with %s and %s',
                               datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), type(inst), inst.args)
                response = jsonify({'Status': 'File Error',
                                    'Message': 'Cannot open log file'})
                response.status_code = 500
                return response
        if auxComp == 'lsf':
            try:
                clog = open(lsflog, 'w+')
            except Exception as inst:
                app.logger.error('[%s] : [ERROR] Opening lsf log with %s and %s',
                                 datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), type(inst), inst.args)
                response = jsonify({'Status': 'File Error',
                                    'Message': 'Cannot open log file'})
                response.status_code = 500
                return response

        return send_file(clog, mimetype='text/plain', as_attachment=True)


@agent.route('/v1/conf/<auxComp>')
@api.doc(params={'auxComp': 'Can be collectd or lsf'})
class NodeMonitConf(Resource):
    def get(self, auxComp):
        if not aux.check(auxComp):
            response = jsonify({'Status': 'Parameter error',
                                'Message': 'Unsupported Parameter' + auxComp})
            app.logger.warning('[%s] : [WARN] Unsupported parameter: %s',
                               datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(auxComp))
            response.status_code = 400
            return response
        if auxComp == 'collectd':
            try:
                cConf = open(collectdConf, 'r')
            except Exception as inst:
                # print >> sys.stderr, type(inst)
                # print >> sys.stderr, inst.args
                app.logger.error('[%s] : [ERROR] Opening collectd conf file',
                                 datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
            return send_file(cConf, mimetype='text/plain', as_attachment=True)
        if auxComp == 'lsf':
            try:
                lConf = open(lsfConf, 'r')
            except Exception as inst:
                # print >> sys.stderr, type(inst)
                # print >> sys.stderr, inst.args
                app.logger.error('[%s] : [ERROR] Opening logstash-forwarder conf file',
                                 datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
            return send_file(lConf, mimetype='application/json', as_attachment=True)
        if auxComp == 'jmx':  # TODO: jmxtrans handeling
            return 'jmx'


@agent.route('/v1/check')
class NodeCheck(Resource):  # TODO: implement check functionality
    def get(self):
        rCollectd = aux.checkAux('collectd')
        rLSF = aux.checkAux('logstash-forwarder')
        response = jsonify({'Collectd': rCollectd,
                            'LSF': rLSF})
        response.status_code = 200
        return response


@agent.route('/v1/bdp/<platform>')  #TODO: Needs testing
@api.doc(params={'platform': 'Can be yarn or spark'})
class AgentMetricsSystem(Resource):
    @api.expect(sparkProperties)
    def post(self, platform):
        if not request.json:
            response = jsonify({'Status': 'Request Error',
                                'Message': 'Request body must be JSON'})
            app.logger.warrning('[%s] : [WARN] Invalid request content-type: %s',
                                datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(request.content_type))
            response.status_code = 400
            return response
        BDService = BDPlatform(tmpDir)
        if platform == 'yarn':
            if not BDService.checkRole('yarn'):
                response = jsonify({'Status': 'Error',
                                    'Message': 'Yarn not detected!'})
                app.logger.warning('[%s] : [WARN] No YARN detected',
                                    datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
                response.status_code = 404
                return response
            if 'Period' not in request.json:
                response = jsonify({'Status': 'Request Error',
                                'Message': 'Must contain Period field'})
                app.logger.error('[%s] : [ERROR] Period must be specified',
                                 datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
                response.status_code = 400
                return response
            settingsDict = {'metrics2_period': request.json['Period']}
            app.logger.info('[%s] : [INFO] Period is set to: %s',
                            datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(request.json['Period']))
            BDService.generateYarnConfig(settingsDict)
            response = jsonify({'Status': 'Done',
                            'Message': 'Yarn properties uploaded'})
            response.status_code = 200
            return response
        if platform == 'spark':
            if not BDService.checkRole('spark'):
                response = jsonify({'Status': 'Error',
                                    'Message': 'Spark not detected!'})
                app.logger.warning('[%s] : [WARN] No Spark detected',
                                    datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
                response.status_code = 404
                return response
            if 'Period' or 'LogstashIP' or 'GraphitePort' not in request.json:
                response = jsonify({'Status': 'Request Error',
                                'Message': 'Must contain Period, Logstash IP and Graphite Port fields'})
                app.logger.error('[%s] : [ERROR] No period, Logstash IP or graphite port fields detected',
                                 datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
                response.status_code = 400
                return response
            settingsDict = {'logstashserverip': request.json['LogstashIP'],
                        'logstashportgraphite': request.json['GraphitePort'],
                        'period': request.json['Period']}
            app.logger.info('[%s] : [INFO] Spark settings: ',
                            datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), str(settingsDict))
            BDService.generateSparkConfig(settingsDict)
            response = jsonify({'Status': 'Done',
                            'Message': 'Spark properties uploaded'})
            response.status_code = 200
            return response
        else:
            response = jsonify({'Status': 'Unsupported',
                                'Message': 'Platform Unsupported'})
            app.logger.error('[%s] : [ERROR] Unsuported platform',
                                    datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'))
            response.status_code = 404
            return response

# logstash-fowarder certificates
@agent.route('/v1/lsf/cert')
class LSFCertificate(Resource):
    def get(self):
        certificateName = []
        for filename in os.listdir(certDir):
            if not os.path.isdir(filename):
                certificateName.append(filename)
                
        response = jsonify({'Certificates': certificateName})
        response.status_code = 200
        return response

    def put(self):
        if request.headers['Content-Type'] == 'application/x-pem-file':
            pemData = request.data
        else:
            app.logger.error('[%s] : [ERR] Bad content type. Expected application/x-pem-file, received %s.',
                                    datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), request.headers['Content-Type'])
            abort(400)
            
        certificateFile = certLoc
        
        if os.path.exists(certificateFile):
            try:
                shutil.copyfile(certificateFile, certificateFile+'.bak')
            except IOError as exception:
                app.logger.error('[%s] : [ERR] File I/O Exception: Unable to backup file: %s. Details: %s',
                                    datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), certificateFile, exception)
                
                response = jsonify({'File I/O Exception: Unable to backup file ' + certificateFile + ' \nDetails: ' + exception})
                response.status_code = 500
                return response    

        try:
            cert = open(certificateFile, 'w+')
            cert.write(pemData)
            cert.close()
        except IOError:
            app.logger.error('[%s] : [ERR] File I/O Exception: Unable to open file %s in w+ mode. Details: %s',
                                    datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), certificateFile, exception)

            response = jsonify({'File I/O Exception: Unable to open file ' + certificateFile + ' in w+ mode.' + ' \nDetails: ' + exception})
            response.status_code = 500
            return response    

        app.logger.info('[%s] : [INFO] Logstash forwarder certificate at %s has been successfully updated.',
                                    datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S'), certificateFile)

        response = jsonify({'Status': 'Logstash forwarder certificate at ' + certificateFile + ' has been successfully updated.'})
        response.status_code = 201
        return response

@agent.route('/v1test')
class Test(Resource):
    def get(self):
        test = {}
        test[logDir] = os.path.isfile(logDir)
        test[tmpDir] = os.path.isfile(tmpDir)
        test[pidDir] = os.path.isfile(pidDir)
        test[os.path.join(logDir, 'dmon-agent.log')] = os.path.isfile(os.path.join(logDir, 'dmon-agent.log'))
        test[collectdlog] = os.path.isfile(collectdlog)
        test[collectdpid] = os.path.isfile(collectdpid)
        test[lsflog] = os.path.isfile(lsflog)
        test[lsferr] = os.path.isfile(lsferr)
        test[collectdConf] = os.path.isfile(collectdConf)
        test[lsfConf] = os.path.isfile(lsfConf)
        test[lsfList] = os.path.isfile(lsfList)
        test[lsfGPG] = os.path.isfile(lsfGPG)
        test[certLoc] = os.path.isfile(certLoc)
        return test


if __name__ == '__main__':
    handler = RotatingFileHandler(os.path.join(logDir, 'dmon-agent.log'), maxBytes=10000000, backupCount=5)
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    app.run(host='0.0.0.0', port=5222, debug=True)
