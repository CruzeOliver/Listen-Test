import sys
import numpy as np
import pyaudio
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
import math
import threading
import pyqtgraph as pg
from UI.Ui_Listen_Test import Ui_MainWindow

class AudioThread(QThread):
    """
    一个独立的线程，用于处理音频播放，防止GUI冻结。
    A separate thread to handle audio playback to prevent the GUI from freezing.
    """
    finished = pyqtSignal()

    def __init__(self, frequency, db_level):
        super().__init__()
        self.frequency = frequency
        self.db_level = db_level
        self.running = True
        self.playing = False
        self.p = None
        self.stream = None
        self.sample_rate = 44100
        self.output_device_index = -1
        self.lock = threading.Lock()

    def run(self):
        """
        生成并播放一个连续的正弦波。
        Generates and plays a continuous sine wave.
        """
        self.p = pyaudio.PyAudio()

        try:
            default_device_info = self.p.get_default_output_device_info()
            self.output_device_index = default_device_info['index']
        except IOError:
            print("No default audio output device found.")
            self.finished.emit()
            return

        self.stream = self.p.open(format=pyaudio.paInt16,
                                  channels=1,
                                  rate=self.sample_rate,
                                  output=True,
                                  output_device_index=self.output_device_index)

        while self.running:
            if self.playing:
                self.lock.acquire()
                amplitude = 10**(self.db_level / 20.0)
                t = np.arange(self.sample_rate * 0.1) / self.sample_rate # Generate a small chunk of audio
                waveform = amplitude * np.sin(2 * np.pi * self.frequency * t)
                audio_data = (waveform * 32767).astype(np.int16).tobytes()
                self.lock.release()
                self.stream.write(audio_data)
            else:
                self.p.get_default_output_device_info() # Check for device existence
                self.msleep(10) # Wait a bit to not burn CPU

        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
        if self.p is not None:
            self.p.terminate()
        self.finished.emit()

    def stop(self):
        """
        停止音频播放循环。
        Stops the audio playback loop.
        """
        self.running = False

    def start_playing(self):
        """
        开始播放音频。
        Starts audio playback.
        """
        self.playing = True

    def stop_playing(self):
        """
        停止播放音频。
        Stops audio playback.
        """
        self.playing = False

    def update_parameters(self, frequency, db_level):
        """
        动态更新频率和分贝。
        Dynamically updates the frequency and decibel level.
        """
        with self.lock:
            self.frequency = max(50.0, min(6000.0, frequency)) # Clamp frequency
            self.db_level = max(-10.0, min(120.0, db_level)) # Clamp decibel level

class MyMainForm(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MyMainForm, self).__init__(parent)
        self.setupUi(self)
        self.setWindowTitle("监听测试")
        self.audio_thread = None
        self.freq_timer = QTimer()
        self.db_timer = QTimer()
        self.freq_delta = 0
        self.db_delta = 0
        self.is_testing = False

        # Set initial values
        self.lineEdit_frequency.setText("100")
        self.lineEdit_db.setText("-2")

        self.pushButton_Start.clicked.connect(self.startTest)
        self.pushButton_Stop.clicked.connect(self.stopTest)
        self.pushButton_Stop.setEnabled(False)

        self.freq_timer.timeout.connect(self.adjust_frequency)
        self.db_timer.timeout.connect(self.adjust_db)

        # Initialize pyqtgraph plot
        self.graph_widget = pg.PlotWidget()
        layout = QVBoxLayout(self.widget_listenPlot)
        layout.addWidget(self.graph_widget)
        self.graph_widget.setBackground('w')
        self.graph_widget.setTitle("听力测试结果", color="#000000", size="18pt")
        self.graph_widget.setLabel('left', '分贝', units='dB')
        self.graph_widget.setLabel('bottom', '频率', units='Hz')
        self.graph_widget.showGrid(x=True, y=True)

        # Plot items for different symbols
        self.plot_item = self.graph_widget.plot(pen=None, symbol='o', symbolSize=15, symbolBrush=('b'))
        self.x_plot_item = self.graph_widget.plot(pen=None, symbol='x', symbolSize=15, symbolBrush=('r'))

        self.plot_data_points = []
        self.x_plot_data_points = []
        self.graph_widget.setXRange(50, 6000, padding=0)
        self.graph_widget.setYRange(-10, 120, padding=0)


    def startTest(self):
        """
        根据用户输入开始音频播放线程。
        Starts the audio playback thread based on user input.
        """
        if self.is_testing:
            return

        try:
            freq = float(self.lineEdit_frequency.text())
            db = float(self.lineEdit_db.text())

            self.textEdit_logMessage.append(f"测试准备就绪：频率 {freq} Hz, 分贝 {db} dB。请按住空格键开始听音。")

            self.audio_thread = AudioThread(freq, db)
            self.audio_thread.finished.connect(self.on_thread_finished)
            self.audio_thread.start()

            self.is_testing = True
            self.pushButton_Start.setEnabled(False)
            self.pushButton_Stop.setEnabled(True)
            self.setFocus() # Set focus to the main window to enable keyboard events

            # Reset plot for new test
            self.plot_data_points = []
            self.x_plot_data_points = []
            self.plot_item.setData([], [])
            self.x_plot_item.setData([], [])

        except ValueError:
            self.textEdit_logMessage.append("输入无效！频率和分贝必须为数字。")

    def stopTest(self):
        """
        停止音频播放线程。
        Stops the audio playback thread.
        """
        if self.is_testing:
            self.textEdit_logMessage.append("停止测试。")
            self.audio_thread.stop()
            self.is_testing = False
            self.freq_timer.stop()
            self.db_timer.stop()

    def on_thread_finished(self):
        """
        处理线程结束，重新启用按钮。
        Slot to handle the thread finishing, re-enabling buttons.
        """
        self.pushButton_Start.setEnabled(True)
        self.pushButton_Stop.setEnabled(False)
        self.freq_timer.stop()
        self.db_timer.stop()

    def keyPressEvent(self, event):
        """
        处理按键按下事件，持续改变频率或分贝。
        Handles key press events to continuously change frequency or decibel.
        """
        if not self.is_testing:
            return

        if event.key() == Qt.Key_W and not self.freq_timer.isActive():
            self.freq_delta = 10
            self.freq_timer.start(50) # Adjust every 50ms
        elif event.key() == Qt.Key_S and not self.freq_timer.isActive():
            self.freq_delta = -10
            self.freq_timer.start(50)
        elif event.key() == Qt.Key_Up and not self.db_timer.isActive():
            self.db_delta = 1
            self.db_timer.start(50)
        elif event.key() == Qt.Key_Down and not self.db_timer.isActive():
            self.db_delta = -1
            self.db_timer.start(50)
        elif event.key() == Qt.Key_Space:
            if self.audio_thread and not self.audio_thread.playing:
                self.textEdit_logMessage.append("正在播放声音...")
                self.audio_thread.start_playing()
        elif event.key() == Qt.Key_Return and self.audio_thread and self.audio_thread.playing:
            current_freq = float(self.lineEdit_frequency.text())
            current_db = float(self.lineEdit_db.text())
            self.x_plot_data_points.append((current_freq, current_db))
            x_data = [p[0] for p in self.x_plot_data_points]
            y_data = [p[1] for p in self.x_plot_data_points]
            self.x_plot_item.setData(x_data, y_data)
            self.textEdit_logMessage.append(f"已用“x”标记数据点: ({current_freq} Hz, {current_db} dB)")

    def keyReleaseEvent(self, event):
        """
        处理按键释放事件，停止改变。
        Handles key release events to stop changes.
        """
        if not self.is_testing:
            return

        if event.key() == Qt.Key_W or event.key() == Qt.Key_S:
            self.freq_delta = 0
            self.freq_timer.stop()
        elif event.key() == Qt.Key_Up or event.key() == Qt.Key_Down:
            self.db_delta = 0
            self.db_timer.stop()
        elif event.key() == Qt.Key_Space:
            if self.audio_thread and self.audio_thread.playing:
                self.textEdit_logMessage.append("停止播放声音。")
                self.audio_thread.stop_playing()

                # Plot the point
                current_freq = float(self.lineEdit_frequency.text())
                current_db = float(self.lineEdit_db.text())
                self.plot_data_points.append((current_freq, current_db))
                x_data = [p[0] for p in self.plot_data_points]
                y_data = [p[1] for p in self.plot_data_points]
                self.plot_item.setData(x_data, y_data)
                self.textEdit_logMessage.append(f"已记录数据点: ({current_freq} Hz, {current_db} dB)")

    def adjust_frequency(self):
        """
        调整频率。
        Adjusts the frequency.
        """
        current_freq = float(self.lineEdit_frequency.text())
        new_freq = current_freq + self.freq_delta
        self.lineEdit_frequency.setText(str(int(max(50, min(6000, new_freq)))))
        self.audio_thread.update_parameters(new_freq, float(self.lineEdit_db.text()))

    def adjust_db(self):
        """
        调整分贝。
        Adjusts the decibel level.
        """
        current_db = float(self.lineEdit_db.text())
        new_db = current_db + self.db_delta
        self.lineEdit_db.setText(str(int(max(-10, min(120, new_db)))))
        self.audio_thread.update_parameters(float(self.lineEdit_frequency.text()), new_db)

    def closeEvent(self, event):
        """
        确保应用程序关闭时音频线程停止。
        Ensures the audio thread is stopped when the application is closed.
        """
        self.stopTest()
        if self.audio_thread:
            self.audio_thread.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    myWin = MyMainForm()
    myWin.show()
    sys.exit(app.exec_())
