# Stream assembler

A socket server that sends a combined stream of all available webcam streams on the network to its subscribed clients. The client can request for any combination of the webcam streams or even just one and this program will generate the frame and send it to the client.

To run, specify the port you want the application to broadcast the stream on, the output size of the stream and any number of IPs that are streaming on the same network.

This application has been developed to run in sync with the [webcam-over-ip](https://github.com/adrianvellamlt/webcam-over-ip) code base.

```
Invoke:

python stream-assembler {port} {height}x{width} {webcam-n-ip}:{webcam-n-port} ...

Example:

python stream-assembler 8080 480x640 192.168.1.98:8089 198.168.1.99:8089
```

## Notes:

- The application was tested with 3 webcam streams. 
- Up to 5 clients are permitted. More are possible but in my use case, this was not needed so I limited to 5.