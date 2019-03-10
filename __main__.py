import socket
from threading import Thread
from sys import argv, platform
from streamHandler import ReadWebcamOverIP, RTSP

def main():
    if len(argv) < 4: 
        raise Exception("At least a port, an output_size and one ip:port are required.")
    
    port = int(argv[1])

    output_size = argv[2].split("x")
    output_size = (int(output_size[0]), int(output_size[1]))

    webcam_streams = []
    for stream_info in argv[3:]:
        info = stream_info.split(":")
        webcam_streams.append((info[0], int(info[1])))

    streamTasks = []
    for webcam_stream in webcam_streams:
        tsk = ReadWebcamOverIP(output_size, webcam_stream)
        tsk.start()
        streamTasks.append(tsk)

    rtsp_tsk = RTSP(output_size, streamTasks, port)
    rtsp_tsk.start()

if __name__ == "__main__":
    main()