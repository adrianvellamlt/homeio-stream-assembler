from os import environ
from threading import Thread
from socket import gethostbyname
from streamHandler import ReadWebcamOverIP, TCP

def main():

    print(environ["PORT"], environ["STREAM_SIZE"], environ["STREAM_IPS"])

    port = int(environ["PORT"])

    output_size = environ["STREAM_SIZE"].split("x")
    output_size = (int(output_size[0]), int(output_size[1]))

    webcam_streams = []
    for stream_info in environ["STREAM_IPS"].split(","):
        info = stream_info.split(":")
        webcam_streams.append((gethostbyname(info[0]), int(info[1])))

    streams = { }
    for webcam_stream in webcam_streams:
        tsk = ReadWebcamOverIP(output_size, webcam_stream)
        tsk.start()
        streams[webcam_stream[0]+":"+str(webcam_stream[1])] = tsk

    tcp_tsk = TCP(output_size, streams, port)
    tcp_tsk.start()

if __name__ == "__main__":
    main()