import re
import os
import sys
import time
import socket
import threading
from utils.logtools import LogTool

class ClientThread(threading.Thread):

  def __init__(self, server_addr, server_port):
    super().__init__()
    self.server_addr = server_addr
    self.server_port = server_port
    self.controlSock = None
    self.bufSize = 1024
    self.connected = False
    self.loggedIn = False
    self.dataAddr = None
    self.current_dir = ''
    self.msg_coding = 'ascii'
    self.log = LogTool("client.log")

  def confirm(self, get_replay = False):
    if self.controlSock is None:
      return False
    try:
      reply = self.controlSock.recv(self.bufSize).decode(self.msg_coding)
    except socket.timeout:
      return False
    else:
      if 0 < len(reply):
        reply = reply.strip()
        if reply.split()[0] == '[Error]':
          if not self.log.screen_print: print('Server: ' + reply)
          self.log.write('Server:' + reply, color='Red')
        else:
          self.log.write('Server:' + reply)
        if get_replay: return reply.split()[0] != '[Error]', reply
        return reply.split()[0] != '[Error]'
      else:  # Server disconnected
        self.connected = False
        self.loggedIn = False
        self.controlSock.close()
        self.controlSock = None

  def connect(self, host, port):
    if self.controlSock is not None:  # Close existing socket first
      self.connected = False
      self.loggedIn = False
      self.controlSock.close()
    self.controlSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    self.controlSock.connect((host, port))
    if self.confirm():
      self.connected = True
      self.controlSock.settimeout(3)  # Timeout 1 second
      self.controlSock.send(b'establish')
      confirmed, reply = self.confirm(get_replay=True)
      if confirmed:
        try:
          # m = re.search(r'(\d+).(\d+).(\d+).(\d+):(\d+),(\d+)', reply)
          # self.dataAddr = (m.group(1) + '.' + m.group(2) + '.' + m.group(3) +
          #                  '.' + m.group(4), int(m.group(5)) * 256 + int(m.group(6)))
          m = re.search(r'(\d+).(\d+).(\d+).(\d+):(\d+)', reply)
          self.dataAddr = (m.group(1) + '.' + m.group(2) + '.' + m.group(3) +
                           '.' + m.group(4), int(m.group(5)))
        except:
          self.log.write("[Error] Can't setup data connection!", color='Red')

  def login(self):
    if not self.connected:
      return
    self.loggedIn = False
    self.controlSock.send('login Zjk Zjk'.encode(self.msg_coding))
    if self.confirm():
      self.loggedIn = True

  def close(self):
    if not self.connected:
      return
    self.controlSock.send(b'close\r\n')
    self.confirm()
    self.connected = False
    self.loggedIn = False
    self.controlSock.close()
    self.controlSock = None

  def pwd(self, is_print = True):
    if not self.connected or not self.loggedIn:
      return
    self.controlSock.send(b'pwd\r\n')
    confirmed, reply = self.confirm(get_replay=True)
    if is_print: print(reply.split()[1])
    self.current_dir = reply.split()[1]

  def cd(self, path):
    if not self.connected or not self.loggedIn:
      return
    self.controlSock.send(('cd %s\r\n' % path).encode(self.msg_coding))
    confirmed, reply = self.confirm(get_replay=True)
    if confirmed: self.current_dir = reply.split()[1]

  def help(self):
    if not self.connected or not self.loggedIn:
      return
    self.controlSock.send(b'help\r\n')
    self.confirm()

  def ls(self, cmd):
    if not self.connected or not self.loggedIn:
      return
    dataSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    dataSock.connect(self.dataAddr)
    self.controlSock.send('{} \r\n'.format(cmd).encode(self.msg_coding))
    time.sleep(0.5)  # Wait for connection to set up
    dataSock.setblocking(False)  # Set to non-blocking to detect connection close
    while True:
      try:
        data = dataSock.recv(self.bufSize)
        if len(data) == 0:  # Connection close
          break
        data = data.decode('utf8').split()
        for i in range(0,len(data) - 1,2):
          print('{:<30}{:<30}'.format(data[i], data[i + 1]))
        if len(data) % 2: print(data[-1])
      except socket.error:  # Connection closed
        break
    dataSock.close()
    self.confirm()

  def get(self, filename):
    if not self.connected or not self.loggedIn:
      return
    if os.path.exists(filename):
      self.log.write('[Error] File Already Exists!', color='Red')
      return
    dataSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    dataSock.connect(self.dataAddr)
    self.controlSock.send(('get %s\r\n' % filename).encode(self.msg_coding))
    fileOut = open(filename, 'wb')
    time.sleep(0.5)  # Wait for connection to set up
    dataSock.setblocking(False)  # Set to non-blocking to detect connection close
    while True:
      try:
        data = dataSock.recv(self.bufSize)
        if len(data) == 0:  # Connection close
          break
        fileOut.write(data)
      except socket.error:  # Connection closed
        break
    fileOut.close()
    dataSock.close()
    self.confirm()

  def put(self, filename):
    if not self.connected or not self.loggedIn:
      return
    if not os.path.exists(filename):
      self.log.write('[Error] File not exists!', color='Red')
    dataSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    dataSock.connect(self.dataAddr)
    self.controlSock.send(('put %s\r\n' % filename).encode(self.msg_coding))
    dataSock.send(open(filename, 'rb').read())
    dataSock.close()
    self.confirm()

  def mkdir(self, dirname):
    if not self.connected or not self.loggedIn:
      return
    self.controlSock.send(('mkdir %s\r\n' % dirname).encode(self.msg_coding))
    self.confirm()

  def rm(self, filenames):
    if not self.connected or not self.loggedIn:
      return
    self.controlSock.send(('rm %s\r\n' % filenames).encode(self.msg_coding))
    self.confirm()

  def run(self):
    self.connect(self.server_addr, self.server_port)
    self.login()
    self.pwd(is_print=False)
    while True:
      try:
        cmd = input('ftp > ' + self.current_dir + ':')
        cmdHead = cmd.split()[0].lower()
        self.log.write('>>' + cmd, force_unprint=True)
        if cmdHead == 'close':  # QUIT
          self.close()
          break
        elif cmdHead == 'help':  # HELP
          self.help()
        elif cmdHead == 'pwd':  # PWD
          self.pwd()
        elif cmdHead == 'cd':  # CWD
          self.cd(cmd.split()[1])
        elif cmdHead == 'ls':  # NLST
          self.ls(cmd)
        elif cmdHead == 'get':
          self.get(cmd.split()[1])
        elif cmdHead == 'put':
          self.put(cmd.split()[1])
        elif cmdHead == 'mkdir': # MKDIR
          self.mkdir(cmd.split()[1])
        elif cmdHead == 'rm':
          self.rm(' '.join(cmd.split()[1:]))
        elif cmdHead == 'debug':
          self.log.screen_print = int(cmd.split()[1])
        else:
          self.log.write('unknown command' + cmd, color='Red')
      except IndexError:
        self.log.write('[Error] Too few argument', color='Red')
      except ValueError:
        self.log.write('[Error] Value Error', color='Red')


if __name__ == '__main__':
  ClientThread("0.0.0.0", 23333).start()


