import io
import cv2
import numpy
import socket
import struct
import pickle
import base64
from PIL import Image
from time import sleep
from sys import platform
from threading import Thread
from subprocess import run, PIPE
from numpy import zeros, uint8, hstack, vstack

server = None
tcp_clients = []

def CombineStreams(output_size, columns, rows, streams):
    blankImg = zeros((output_size[0], output_size[1], 3), dtype=uint8)

    current_stream = 0

    combinedImg = None
    for col_indx in range(columns):
        combinedRow = None

        for row_indx in range(rows):
            stream = blankImg if current_stream > (len(streams) - 1) else streams[current_stream].read()
            cv2.rectangle(stream, (0, 0), (stream.shape[1], stream.shape[0]), (255, 255, 255), 2)
            if combinedRow is None:
                combinedRow = stream
            else:
                combinedRow = hstack((combinedRow, stream))
            current_stream += 1

        if combinedImg is None:
            combinedImg = combinedRow
        else:
            combinedImg = vstack((combinedImg, combinedRow))

    return cv2.resize(combinedImg, (output_size[1], output_size[0]))

class ReadWebcamOverIP(Thread):
    def __init__(self, output_size, ip_port):
        self.ip = ip_port[0]
        self.port = ip_port[1]
        self.output_size = (output_size[0], output_size[1], 3)

        self.running = True
        self.clientsocket = None

        offlineStreamImg = zeros(self.output_size, dtype=uint8)
        textsize = cv2.getTextSize("Stream Offline", cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        centreCoords = ( int((self.output_size[1] - textsize[0]) / 2), int((self.output_size[0] + textsize[1]) / 2) )
        cv2.putText(offlineStreamImg, "Stream Offline", centreCoords, cv2.FONT_HERSHEY_SIMPLEX, 1, (69, 53, 220), 2)
        self.offlineStreamImg = offlineStreamImg
        
        self.imgToShow = self.offlineStreamImg

        super(ReadWebcamOverIP, self).__init__(name = "Reading stream {ip}:{port}".format(ip=self.ip, port=self.port))

    def read(self): 
        sleep(0.001) # important for resource conservation
        if self.imgToShow.shape[0] != self.output_size[0] or self.imgToShow.shape[1] != self.output_size[1]: 
            return cv2.resize(self.imgToShow, (self.output_size[1], self.output_size[0]))
        else: return self.imgToShow

    def stop(self): self.running = False

    def setup(self):
        try:
            clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            clientsocket.settimeout(5)
            clientsocket.connect((self.ip, self.port))
            print("Connected to server.")
            self.clientsocket = clientsocket
        except Exception as err:
            print("Unable to connect to {ip}:{port}. Max clients reached?".format(ip=self.ip, port=self.port), str(err))

    def teardown(self):
        self.clientsocket.close()
        self.clientsocket = None

    def run(self):
        while self.running:
            data = b''
            payload_size = struct.calcsize("L")

            if self.clientsocket is not None:
                try:
                    while self.running:
                        emptyResponses = 0
                        while len(data) < payload_size:
                            response = self.clientsocket.recv(4096)
                            if response == b'':
                                emptyResponses += 1
                                if emptyResponses > 10: 
                                    self.teardown()
                                    break
                            else: emptyResponses = 0
                            data += response
                        if self.clientsocket is None: 
                            break
                        else:
                            packed_msg_size = data[:payload_size]

                            data = data[payload_size:]
                            msg_size = struct.unpack("L", packed_msg_size)[0]

                            while len(data) < msg_size:
                                data += self.clientsocket.recv(4096)

                            frame_data = data[:msg_size]
                            data = data[msg_size:]

                            self.imgToShow = pickle.loads(frame_data)
                except:
                    self.clientsocket = None
            else:
                self.imgToShow = self.offlineStreamImg
                self.setup()

class TCP(Thread):
    def __init__(self, output_size, streams, server_port):
        self.output_size = output_size
        self.streams = streams
        self.server_port = server_port
        self.lookupThread = None
        self.running = True
        super(TCP, self).__init__(name = "TCP")

    def stop(self): 
        self.running = False

    def setup(self):
        global server

        address = socket.gethostbyname(socket.gethostname())
        if address.startswith("127.") and (platform == "linux" or platform == "linux2"):
            # if result is loopback and system is linux, get first name returned by 'hostname -I'
            address = str(run("hostname -I", shell=True, stdout=PIPE).stdout).split(" ")[0]
            address = address.replace("\\n", "").replace(" ", "")[2:]
        
        print(address, self.server_port)
        server = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        server.bind((address, self.server_port))
        server.listen(10)

        self.lookupThread = TCPClientLookup()
        self.lookupThread.start()

    def teardown(self):
        global server
        global tcp_clients

        self.lookupThread.stop()
        for client in tcp_clients:
            client[0].close()
        server.close()

    def run(self):
        global tcp_clients

        try:
            while self.running:
                self.setup()
                while self.running:
                    for client in tcp_clients:
                        try:
                            clientStreams = client[2][2]
                            streamsToCombine = []
                            for clientStream in clientStreams:
                                if clientStream in self.streams: streamsToCombine.append(self.streams[clientStream])

                            if (len(streamsToCombine) > 0):
                                frame = CombineStreams(self.output_size, client[2][0], client[2][1], streamsToCombine)

                                b64 = "data:image/jpeg;base64," + str(base64.b64encode(cv2.imencode(".jpg", frame)[1].tobytes()))[2:-1]
                                
                                b64Bytes = str.encode(b64)

                                client[0].sendall(b64Bytes)
                        except Exception as err:
                            tcp_clients.remove(client)
                            print ('Connection dropped: ', client[1], err)
                            client[0].close()
                            
                        sleep(0.001) # important for resource conservation
                self.teardown()
        except Exception as err:
            print("TCP Thread stopped:", str(err))

# Clients for the TCP Client to send and receive data from
class TCPClientLookup(Thread):
    def __init__(self):
        self.running = True
        super(TCPClientLookup, self).__init__(name = "TCP Client Lookup")

    def stop(self): self.running = False

    def recvAll(self, conn):
        char = b' '
        buffer = b''
        while char != b'\r':
            char = conn.recv(1)
            buffer = buffer + char
        return buffer.decode("utf-8")[:-1]

    def run(self):
        global server
        global tcp_clients

        try:
            while self.running:
                try:
                    if len(tcp_clients) <= 5:
                        conn, addr = server.accept()
                        print("Connection established to:", addr)

                        print("Waiting for client settings")
                        clientSettings = self.recvAll(conn)
                        settingSegments = clientSettings.split("|")
                        print("Client settings received")

                        streams = settingSegments[0].split(",")
                        grid = settingSegments[1].split("x")
                        
                        tcp_clients.append((conn, addr, (int(grid[0]), int(grid[1]), streams)))
                except Exception as err:
                    print("Server connection dropped")
        except Exception as err:
            print("TCP Client Lookup Thread stopped:", str(err))