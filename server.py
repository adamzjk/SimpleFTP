import os
import sys
import time
import socket
import threading
import shutil
from logtools import LogTool


class ServerThread(threading.Thread):
  ''' FTP server handler '''

  def __init__(self, ctr_socket, cli_addr, log):
    # 1, prep works
    super(ServerThread, self).__init__()
    assert type(log) is LogTool
    assert type(ctr_socket) is socket.socket
    self.daemon = True  # If main thread exit, this thread exit too
    self.buffer_size = 16 * 1024 * 1024
    self.keep_running = True
    self.usr_dir = os.getcwd() #'/Users/Adam'
    os.chdir(self.usr_dir)
    self.original_dir = os.getcwd()

    # 2, control socket for debug communication
    self.ctr_socket = ctr_socket
    self.cli_addr = cli_addr
    self.msg_encode = 'ascii'

    # 3, data socket for data transfering
    self.data_listen_socket = None
    self.data_socket = None
    self.data_addr = '0.0.0.0'
    self.data_port = None

    # 4, info and functions
    self.username = ''
    self.login = False
    self.log = log

  def EstablishDataConnection(self):
    """ Establish a new TCP connection for data transfering
        port number is automatically allocated """
    if self.data_listen_socket is not None:  # Close existing data connection listening socket
      self.data_listen_socket.close()
    self.data_listen_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    self.data_listen_socket.bind((self.data_addr, 0)) # select a port for data connection
    self.data_port = self.data_listen_socket.getsockname()[1]
    self.data_listen_socket.listen(99)
    self.ctr_socket.send(('%s.%s.%s.%s:%d\r\n' % (
      self.data_addr.split('.')[0], self.data_addr.split('.')[1], self.data_addr.split('.')[2],
      self.data_addr.split('.')[3], int(self.data_port))).encode(self.msg_encode))
    (self.data_socket, self.cli_addr) = self.data_listen_socket.accept()
    self.log.write('Data connection accpted from %s:%d.' %
                   (self.cli_addr[0], self.cli_addr[1]), self.cli_addr)

  def _login(self, cmd):
    if len(cmd.split()) < 2:
      self.ctr_socket.send(b'[Error] Syntax error in parameters or arguments.')
    else:
      self.username = cmd.split()[1]
      self.ctr_socket.send(b'User logged in, proceed.')
      self.login = True

  def _help(self):
    self.ctr_socket.send(b'help '
                         b'login '
                         b'close '
                         b'pwd '
                         b'cd '
                         b'ls '
                         b'get '
                         b'put')

  def _pwd(self):
    if not self.login:
      self.ctr_socket.send(b'[Error] Not logged in.\r\n')
    else:
      self.ctr_socket.send(('[dir] {}'.format(os.getcwd())).encode(self.msg_encode))

  def _cd(self, cmd):
    if not self.login:
      self.ctr_socket.send(b'[Error] Not logged in.\r\n')
    elif len(cmd) >= 2:
      os.chdir(os.getcwd())
      newDir = cmd.split()[1].replace('~', self.usr_dir)
      try:
        if newDir == '..':
          os.chdir(os.path.dirname(os.getcwd()))
        elif os.path.exists(os.path.join(os.getcwd(), newDir)):
          os.chdir(os.path.join(os.getcwd(), newDir))
        else:
          os.chdir(newDir)
        self.ctr_socket.send(('[dir] {}'.format(os.getcwd())).encode(self.msg_encode))
      except OSError:
        self.ctr_socket.send(b'[Error] No Such Directionary!')

  def _ls(self, cmd):
    if not self.login:
      self.ctr_socket.send(b'[Error] Not logged in.\r\n')
    else:
      dirs = os.listdir(os.getcwd())
      if len(cmd.split()) < 2 or cmd.split()[1] != '-a':
        dirs = [x for x in dirs if x[0] != '.']
      dirs = ' '.join(dirs)
      self.data_socket.send(dirs.encode('utf8'))
      self.data_socket.close()
      self.data_socket = None
      self.log.write("Transfer Successful, Close connection.")
      self.ctr_socket.send(b'Transfer Successful, Close connection.')

  def _get(self, cmd):
    if not self.login:
      self.ctr_socket.send(b'[Error] Not logged in.')
    elif len(cmd.split()) < 2:
      self.ctr_socket.send(b'[Error] Syntax error in parameters or arguments.')
    else:
      programDir = os.getcwd()
      os.chdir(os.getcwd())
      fileName = cmd.split()[1]
      time_starts = time.time()
      try:
        file_data = open(fileName, 'rb').read()
        sent = 0 # Important! large file might need several sendings
        while sent < len(file_data):
          bytes_send = self.data_socket.send(file_data[sent:])
          sent += bytes_send
        self.log.write("Transmit compleate, average upload speed = {:.3f}Mb/s"
                       .format(len(file_data) / (1024 * 1024 * (time.time() - time_starts)) ))
        self.log.write("Transfer Successful, Close connection.")
        self.ctr_socket.send(b'Transfer Successful, Close connection.')
      except IOError as error:
        self.log.write("IO Error "+str(error), color='Red')
        self.ctr_socket.send(b'[Error] IO Error.')
      except FileNotFoundError:
        self.ctr_socket.send(b'[Error] File Not Found!')
      self.data_socket.close()
      self.data_socket = None
      os.chdir(programDir)

  def _put(self, cmd):
    if not self.login:
      self.ctr_socket.send(b'[Error] Not logged in')
    elif len(cmd.split()) < 2:
      self.ctr_socket.send(b'[Error] Syntax error.')
    elif self.data_socket is not None:  # Only PASV implemented
      programDir = os.getcwd()
      os.chdir(os.getcwd())
      if os.path.exists(cmd.split()[1]):
        ctr_socket.send(b'[Warning] File Already Exists! Now gonna replace it!')
      fileOut = open(cmd.split()[1], 'wb')
      time.sleep(0.5)  # Wait for connection to set up
      time_starts = time.time()
      data_length = 0
      while True:
        try:
          data = self.data_socket.recv(self.buffer_size)
          if data == b'':  # Connection closed
            break
          fileOut.write(data)
          data_length += len(data)
        except socket.error:  # Connection closed
          break
      self.log.write("Transmit compleate, average download speed = {:.3f}Mb/s"
                     .format(data_length / (1024 * 1024 * (time.time() - time_starts)) ))
      fileOut.close()
      self.data_socket.close()
      self.data_socket = None
      self.ctr_socket.send(b'Closing data connection.')
      os.chdir(programDir)
    else:
      self.ctr_socket.send(b"[Error] Can't open data connection.")

  def _mkdir(self, cmd):
    if not self.login:
      self.ctr_socket.send(b'[Error] Not logged in')
    elif len(cmd.split()) < 2:
      self.ctr_socket.send(b'[Error] Syntax error.')
    else:
      os.mkdir(cmd.split()[1])
      self.ctr_socket.send(b'Create Directionary Success!')

  def _rm(self, cmd):
    if not self.login:
      self.ctr_socket.send(b'[Error] Not logged in')
    elif len(cmd.split()) < 2:
      self.ctr_socket.send(b'[Error] Syntax error.')
    else:
      try:
        if cmd.split()[1] == '-r': # remove folder
          for filename in cmd.split()[2:]:
            shutil.rmtree(filename) # WARNING, this will remove all contents inside folder
        else:
          for filename in cmd.split()[1:]: # remove files
            os.remove(filename)
        self.ctr_socket.send(b'Remove Sucessfull')
      except OSError:
        self.ctr_socket.send(b'[Error] OS Error. No Such File')

  def _close(self):
    self.ctr_socket.send(b'Service closing control connection. Logged out if appropriate.')
    self.ctr_socket.close()
    self.log.write('Client disconnected.', self.cli_addr)
    self.log.file.close()
    self.keep_running = False

  def _force_close(self):
    self.ctr_socket.close()
    self.log.write('Client disconnected.', self.cli_addr)
    self.keep_running = False

  def assign_new_port(self):
    listen_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0);
    listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

  def run(self):
    self.ctr_socket.send(b'Connection Set!')
    while self.keep_running:
      cmd = self.ctr_socket.recv(self.buffer_size).decode(self.msg_encode)
      if cmd == '':  # Connection closed
        self.log.write("Receive nothing, connection closed.", self.cli_addr, color='Red')
        self._force_close()
        break
      elif cmd == 'establish':
        self.EstablishDataConnection()
        continue
      elif cmd is None or len(cmd) <= 1: # some error...
        self.log.write("[Error] receive Error", color='Red')
        continue
      self.log.write('[' + (self.username if self.login else '') + '] ' + cmd.strip(), self.cli_addr)
      cmd_head = cmd.split()[0].lower() if cmd else None
      if cmd_head == 'close':  # QUIT
        self._close()
      elif cmd_head == 'help':  # HELP
        self._help()
      elif cmd_head == 'login':
        self._login(cmd)
      elif cmd_head == 'pwd':  # PWD
        self._pwd()
      elif cmd_head == 'cd':  # CWD
        self._cd(cmd)
      elif cmd_head == 'ls':  # NLST
        self._ls(cmd)
      elif cmd_head == 'get':
        self._get(cmd)
      elif cmd_head == 'put':
        self._put(cmd)
      elif cmd_head == 'mkdir':
        self._mkdir(cmd)
      elif cmd_head == 'rm':
        self._rm(cmd)
      else:
        self.ctr_socket.send(('[Error] Unrecognized Command: '
                              + cmd_head).encode(self.msg_encode))


if __name__ == '__main__':
  server_addr = '0.0.0.0'
  server_port = 24678
  server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
  server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
  server_socket.bind((server_addr, server_port))
  server_socket.listen(5)
  log = LogTool("server.log", screen_print=True)
  log.write('Server started.')
  while True:
    (ctr_socket, client_addr) = server_socket.accept()
    ServerThread(ctr_socket, client_addr, log).start()
    log.write("Connection accepted.", client_addr)

