import io
import cv2
import numpy
import socket
import struct
import pickle
import base64
from time import sleep
from sys import platform
from threading import Thread
from collections import namedtuple
from numpy import zeros, uint8, hstack, vstack

server = None
tcp_clients = []

# combines streams into the specified grid and returns an image/ frame.
def CombineStreams(output_size, columns, rows, streams):
    boxWidth = output_size[1] // columns
    boxHeight = output_size[0] // rows

    blankImg = zeros((boxHeight, boxWidth, 3), dtype=uint8)

    current_stream = 0

    combinedImg = None
    for col_indx in range(columns):
        combinedRow = None

        for row_indx in range(rows):
            stream = blankImg if current_stream > (len(streams) - 1) else cv2.resize(streams[current_stream].read(), (boxWidth, boxHeight))
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

# reads frames from webcams over ip. (homeio-webcam-over-ip)
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
                        sleep(0.03)
                        # fill buffer up to payload size
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

                        # if client socket, teardown and start again
                        if self.clientsocket is None: 
                            break
                        else:
                            # get packed message size
                            packed_msg_size = data[:payload_size]

                            # get message without size prefix
                            data = data[payload_size:]

                            # unpack msg size prefix
                            msg_size = struct.unpack("L", packed_msg_size)[0]

                            # read data until msg size is read
                            while len(data) < msg_size:
                                data += self.clientsocket.recv(4096)

                            # slice msg size from data to form a frame
                            frame_data = data[:msg_size]
                            data = data[msg_size:]

                            self.imgToShow = pickle.loads(frame_data)
                except:
                    # tearing down. if thread is still running, we will setup again (hence reconnecting).
                    self.teardown()
            else:
                self.imgToShow = self.offlineStreamImg
                self.setup()

# tcp server that sends data to one or more clients
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
        
        server = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        server.bind(("", self.server_port))
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

        ConnectionInfo = namedtuple("ConnectionInfo", ["conn", "address"])
        FrameInfo = namedtuple("FrameInfo", ["rows", "columns", "streams"])

        try:
            while self.running:
                self.setup()
                while self.running:
                    # if we have no client, wait for 1 second and try again
                    if len (tcp_clients) < 1:
                        sleep(1)
                        continue

                    # get image combinations to generate from tcp_clients
                    framesToGenerate = {}
                    for client in tcp_clients:
                        
                        # client connection and address
                        clientConn = ConnectionInfo(conn = client[0], address = client[1])

                        # streams and output stream grid info
                        frameInfo = FrameInfo(rows = client[2][0], columns = client[2][1], streams = client[2][2])

                        # add to dictionary. this way a unique image is generate only once for multiple clients
                        if frameInfo not in framesToGenerate:
                            framesToGenerate[frameInfo] = [clientConn]
                        else:
                            framesToGenerate[frameInfo].append(clientConn)

                    # iterate over unique images to generate
                    for frameInfo in framesToGenerate:
                        # streams that streamassembler has access and is connected to.
                        # this filters out streams that are not valid. instead of sending back bad request.
                        streamsToCombine = []
                        for clientStream in frameInfo.streams.split(","):
                            if clientStream in self.streams: streamsToCombine.append(self.streams[clientStream])

                        # if any valid streams
                        if len(streamsToCombine) > 0:
                            # generate frame
                            frame = CombineStreams(self.output_size, frameInfo.columns, frameInfo.rows, streamsToCombine)
                            
                            # convert to base64
                            b64 = "data:image/jpeg;base64," + str(base64.b64encode(cv2.imencode(".jpg", frame)[1].tobytes()))[2:-1]
                            
                            # encode it to byte arr
                            b64Bytes = str.encode(b64)

                            # send it to all clients that requested this image
                            for clientConn in framesToGenerate[frameInfo]:
                                try:
                                    clientConn.conn.sendall(b64Bytes)
                                except Exception as err:
                                    tcp_clients.remove((clientConn.conn, clientConn.address, (frameInfo.rows, frameInfo.columns, frameInfo.streams)))
                                    print ('Connection dropped: ', clientConn.address, err)
                                    client[0].close()
                
                # if not running any more or unhandled exception occurred, teardown.
                # if still running, we will setup again. (clears connections)
                self.teardown()
        except Exception as err:
            print("TCP Thread stopped:", str(err))

# clients for the TCP Client to send and receive data from
# should be a different permutation of a stream combination
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

                        streams = settingSegments[0]
                        grid = settingSegments[1].split("x")
                        
                        tcp_clients.append((conn, addr, (int(grid[0]), int(grid[1]), streams)))
                except Exception as err:
                    print("Server connection dropped")
        except Exception as err:
            print("TCP Client Lookup Thread stopped:", str(err))