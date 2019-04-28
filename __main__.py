from threading import Thread
from sys import argv
from streamHandler import ReadWebcamOverIP, TCP

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

    streams = { }
    for webcam_stream in webcam_streams:
        tsk = ReadWebcamOverIP(output_size, webcam_stream)
        tsk.start()
        streams[webcam_stream[0]+":"+str(webcam_stream[1])] = tsk

    tcp_tsk = TCP(output_size, streams, port)
    tcp_tsk.start()

if __name__ == "__main__":
    main()