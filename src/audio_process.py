import pyaudio
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import display, clear_output

# Constants
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100//4
CHUNK = 2048

# Initialize PyAudio
p = pyaudio.PyAudio()

# Find the loopback device
loopback_device_index = None
for i in range(p.get_device_count()):

    device_info = p.get_device_info_by_index(i)

    if "blackhole input" in device_info["name"].lower():
        loopback_device_index = i
        break

if loopback_device_index is None:
    print("Loopback device not found.")
    exit()


fig, ax = plt.subplots()
ydata = []
ln, = ax.plot([], [], 'ro-')


# Open stream
stream = p.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                input_device_index=loopback_device_index)


print("Listening...")

try:
    while True:
        # Read audio data from stream
        data = stream.read(CHUNK)

        # Convert binary data to NumPy array
        audio_data = np.frombuffer(data, dtype=np.int16)
        # Apply FFT
        # fft_result = np.fft.fft(audio_data)
        #
        # # Compute magnitude spectrum
        # magnitude_spectrum = np.abs(fft_result)

        fft_data = np.fft.rfft(audio_data)  # rfft removes the mirrored part that fft generates
        fft_freq = np.fft.rfftfreq(len(audio_data), d=1 / RATE)  # rfftfreq needs the signal data, not the fft data

        plt.plot(fft_freq, np.absolute(fft_data))  # fft_data is a complex number, so the magnitude is computed here
        print(len(fft_freq))
        plt.xlim(np.amin(fft_freq), np.amax(fft_freq))
        fig.canvas.draw()
        plt.pause(0.05)
        fig.canvas.flush_events()
        fig.clear()



except KeyboardInterrupt:
    pass

print("Finished listening.")

# Close stream
stream.stop_stream()
stream.close()

# Terminate PyAudio
p.terminate()