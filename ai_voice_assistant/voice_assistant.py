import pyaudio
import wave
import webrtcvad
import collections
import speech_recognition as sr
import io
import os
import openai
from gtts import gTTS
from playsound import playsound
from dotenv import load_dotenv

load_dotenv()

class AIVoiceAssistant:

    def __init__(self, vad_mode=1, item_limit=None, system_prompt="You are an AI Assistant.", channels=1, rate=16000, chunk_duration_ms=30, padding_duration_ms=500, model='gpt-3.5-turbo', language='en'):
        self.tts = TextToSpeech()
        self.llm = LargeLanguageModelAPI()
        self.vad = webrtcvad.Vad(vad_mode)
        self.FORMAT = pyaudio.paInt16
        self.CHANNELS = channels
        self.RATE = rate
        self.CHUNK_DURATION_MS = chunk_duration_ms
        self.PADDING_DURATION_MS = padding_duration_ms
        self.CHUNK_SIZE = int(self.RATE * self.CHUNK_DURATION_MS / 1000)
        self.CHUNK_BYTES = self.CHUNK_SIZE * 2
        self.NUM_PADDING_CHUNKS = int(self.PADDING_DURATION_MS / self.CHUNK_DURATION_MS)
        self.audio = pyaudio.PyAudio()  
        self.device_index, self.device_name = self.find_microphone()
        self.stream = self.audio.open(format=self.FORMAT, channels=self.CHANNELS,
                                      rate=self.RATE, input=True, input_device_index=self.device_index,
                                      frames_per_buffer=self.CHUNK_SIZE)
        self.system_prompt = system_prompt
        self.messages = [{"role": "system", "content": self.system_prompt}]
        self.item_limit = item_limit

        self.model = model
        self.language = language

    def find_microphone(self):
        keywords = ["Microphone", "Mic", "Input", "Line In"]
        p = pyaudio.PyAudio()

        for keyword in keywords:
            for i in range(p.get_device_count()):
                dev = p.get_device_info_by_index(i)
                if keyword.lower() in dev['name'].lower():
                    return i, dev['name'] 
                
        return None, "No matching device found."

    def add_message(self, role, content):
        self.messages.append({"role": role, "content": content})

        if self.item_limit is None:
            return
        
        system_messages = [message for message in self.messages if message['role'] == 'system']

        adjusted_limit = self.item_limit - len(system_messages)

        other_messages = [message for message in self.messages if message['role'] != 'system']

        if len(other_messages) > adjusted_limit:
            self.messages = system_messages + other_messages[-adjusted_limit:]

    def save_speech(self, voiced_frames, sample_rate):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(self.FORMAT))
            wf.setframerate(sample_rate)
            wf.writeframes(b''.join(voiced_frames))
        buffer.seek(0)
        return buffer
    
    def transcribe_audio(self, audio_buffer):
        recognizer = sr.Recognizer()
        with sr.AudioFile(audio_buffer) as source:
            audio_data = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio_data)

                print(f"Transcription: {text}")

                self.add_message('user', text)

                text_to_speak = self.llm.run_gpt(self.messages, self.model)
                
                print(text_to_speak)

                self.add_message('assistant', text_to_speak)

                self.tts.run_speech(text_to_speak, self.language)

            except sr.UnknownValueError:
                print("Unable to understand speech")
            except sr.RequestError as e:
                print(f"Could not transcribe audio; {e}")
    
    def listen(self):
        ring_buffer = collections.deque(maxlen=self.NUM_PADDING_CHUNKS)
        voiced_frames = []
        triggered = False
        print("Listening...")
        try:
            while True:
                chunk = self.stream.read(self.CHUNK_SIZE)
                is_speech = self.vad.is_speech(chunk, self.RATE)
                
                if not triggered:
                    ring_buffer.append(chunk)
                    if len([frame for frame in ring_buffer if self.vad.is_speech(frame, self.RATE)]) > 0.9 * ring_buffer.maxlen:
                        triggered = True
                        voiced_frames = list(ring_buffer)
                        ring_buffer.clear()
                else:
                    voiced_frames.append(chunk)
                    ring_buffer.append(chunk)
                    if len([frame for frame in ring_buffer if not self.vad.is_speech(frame, self.RATE)]) > 0.9 * ring_buffer.maxlen:
                        triggered = False
                        self.save_and_process(voiced_frames)
                        voiced_frames = []
        finally:
            self.stream.stop_stream()
            self.stream.close()
            self.audio.terminate()
    
    def save_and_process(self, voiced_frames):
        audio_data = self.save_speech(voiced_frames, self.RATE)
        self.transcribe_audio(audio_data)

class TextToSpeech:
    def __init__(self) -> None:
        pass

    def run_speech(self, text_to_speak, language):

        gtts_obj = gTTS(text=text_to_speak, lang=language, slow=False)

        audio_file = "text_to_speech.mp3"
        gtts_obj.save(audio_file)

        playsound(audio_file)

        os.remove(audio_file)

class LargeLanguageModelAPI:

    def __init__(self):
        self.openai_key = os.getenv('OPENAI_API_KEY')
    
    def run_gpt(self, messages, model):

        openai.api_key = self.openai_key
        
        response = openai.ChatCompletion.create(
        model=model,  
        messages=messages
        )

        return response['choices'][0]['message']['content']
