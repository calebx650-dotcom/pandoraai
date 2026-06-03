import { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'com.ighsafety.firenspec',
  appName: 'Spectofire',
  webDir: 'www',
  server: {
    // Points to your live Railway deployment — app runs in a native WebView
    url: 'https://igh-firenspec-production-8e09.up.railway.app',
    cleartext: false,
  },
  ios: {
    contentInset: 'always',
    backgroundColor: '#F2F2F7',
    allowsLinkPreview: false,
  },
  plugins: {
    Camera: {
      presentationStyle: 'fullscreen',
    },
  },
};

export default config;
