// Native Browser Speech Recognition wrapper for Indian Languages (kn-IN, hi-IN, en-IN, ta-IN, te-IN)

declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

export type IndicLanguageCode = 'mix-IN' | 'kn-IN' | 'hi-IN' | 'en-IN' | 'ta-IN' | 'te-IN' | 'mr-IN';

export interface IndicLanguageOption {
  code: IndicLanguageCode;
  label: string;
  nativeName: string;
}

export const INDIC_LANGUAGES: IndicLanguageOption[] = [
  { code: 'en-IN', label: 'English (India)', nativeName: 'English (India)' },
  { code: 'kn-IN', label: 'Kannada (ಕನ್ನಡ)', nativeName: 'Kannada (ಕನ್ನಡ)' },
  { code: 'hi-IN', label: 'Hindi (हिंदी)', nativeName: 'Hindi (हिंदी)' },
  { code: 'ta-IN', label: 'Tamil (தமிழ்)', nativeName: 'Tamil (தமிழ்)' },
  { code: 'te-IN', label: 'Telugu (తెలుగు)', nativeName: 'Telugu (తెలుగు)' },
  { code: 'mr-IN', label: 'Marathi (मराठी)', nativeName: 'Marathi (मराठी)' },
  { code: 'mix-IN', label: 'Code-Mixed (Kanglish/Hinglish)', nativeName: 'Code-Mixed (Kanglish/Hinglish)' },
];

export interface IndicSpeechCallbacks {
  onResult: (transcript: string, isFinal: boolean) => void;
  onError: (error: string) => void;
  onEnd: () => void;
  onStart?: () => void;
}

export class IndicSpeechRecognizer {
  private recognition: any = null;
  private isListening: boolean = false;
  private currentLanguage: IndicLanguageCode = 'mix-IN';

  constructor(language: IndicLanguageCode = 'mix-IN') {
    this.currentLanguage = language;
    const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognitionAPI) {
      this.recognition = new SpeechRecognitionAPI();
      this.recognition.continuous = true;
      this.recognition.interimResults = true;
      this.recognition.lang = language === 'mix-IN' ? 'en-IN' : language;
    }
  }

  public static isSupported(): boolean {
    return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
  }

  public setLanguage(language: IndicLanguageCode): void {
    this.currentLanguage = language;
    if (this.recognition) {
      this.recognition.lang = language === 'mix-IN' ? 'en-IN' : language;
    }
  }

  public start(callbacks: IndicSpeechCallbacks): void {
    if (!this.recognition) {
      callbacks.onError('Web Speech API is not supported in this browser.');
      return;
    }

    if (this.isListening) {
      this.stop();
    }

    this.recognition.lang = this.currentLanguage === 'mix-IN' ? 'en-IN' : this.currentLanguage;

    this.recognition.onstart = () => {
      this.isListening = true;
      if (callbacks.onStart) callbacks.onStart();
    };

    this.recognition.onresult = (event: any) => {
      let interimTranscript = '';
      let finalTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; ++i) {
        const transcriptPart = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcriptPart;
        } else {
          interimTranscript += transcriptPart;
        }
      }

      const combined = finalTranscript || interimTranscript;
      callbacks.onResult(combined.trim(), !!finalTranscript);
    };

    this.recognition.onerror = (event: any) => {
      console.warn('Indic Speech Recognition error:', event.error);
      callbacks.onError(event.error || 'Speech recognition failed');
    };

    this.recognition.onend = () => {
      this.isListening = false;
      callbacks.onEnd();
    };

    try {
      this.recognition.start();
    } catch (err: any) {
      console.error('Failed to start SpeechRecognition:', err);
      callbacks.onError(err.message || 'Could not start microphone listener');
    }
  }

  public stop(): void {
    if (this.recognition && this.isListening) {
      try {
        this.recognition.stop();
      } catch (err) {
        console.warn('Error stopping recognition:', err);
      }
      this.isListening = false;
    }
  }

  public getIsListening(): boolean {
    return this.isListening;
  }
}
