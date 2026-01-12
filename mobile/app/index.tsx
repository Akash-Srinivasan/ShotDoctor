import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Alert } from 'react-native';
import { useRouter } from 'expo-router';
import { testConnection } from '../lib/api';

export default function HomeScreen() {
  const router = useRouter();
  const [apiConnected, setApiConnected] = useState<boolean | null>(null);

  useEffect(() => {
    checkApiConnection();
  }, []);

  const checkApiConnection = async () => {
    const connected = await testConnection();
    setApiConnected(connected);
    if (!connected) {
      Alert.alert(
        'API Not Connected',
        'Make sure your Python API is running and ngrok tunnel is active.\n\nRun: ./scripts/start-dev.sh',
        [{ text: 'Retry', onPress: checkApiConnection }]
      );
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>🏀 FormCheck</Text>
        <Text style={styles.subtitle}>Your AI Basketball Coach</Text>
      </View>

      <View style={styles.statusContainer}>
        <Text style={styles.statusLabel}>API Status:</Text>
        <View style={[
          styles.statusBadge,
          apiConnected === null && styles.statusBadgeLoading,
          apiConnected === true && styles.statusBadgeConnected,
          apiConnected === false && styles.statusBadgeDisconnected,
        ]}>
          <Text style={styles.statusText}>
            {apiConnected === null ? '⏳ Checking...' :
             apiConnected ? '✓ Connected' : '✗ Disconnected'}
          </Text>
        </View>
        <TouchableOpacity onPress={checkApiConnection}>
          <Text style={styles.retryLink}>Retry</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.content}>
        <TouchableOpacity
          style={[styles.mainButton, !apiConnected && styles.mainButtonDisabled]}
          onPress={() => router.push('/record')}
          disabled={!apiConnected}
        >
          <Text style={styles.mainButtonText}>📹 Record Shot</Text>
        </TouchableOpacity>

        <View style={styles.infoBox}>
          <Text style={styles.infoText}>
            Get instant AI feedback on your shooting form
          </Text>
        </View>

        <View style={styles.featuresContainer}>
          <Text style={styles.featuresTitle}>What we analyze:</Text>
          <Text style={styles.featureItem}>✓ Elbow angle & release</Text>
          <Text style={styles.featureItem}>✓ Wrist position</Text>
          <Text style={styles.featureItem}>✓ Knee bend & power</Text>
          <Text style={styles.featureItem}>✓ Overall form rating</Text>
        </View>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerText}>MVP v1.0.0</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
  },
  header: {
    paddingTop: 60,
    paddingBottom: 20,
    alignItems: 'center',
  },
  title: {
    fontSize: 48,
    fontWeight: 'bold',
    color: '#ff6b00',
  },
  subtitle: {
    fontSize: 18,
    color: '#fff',
    marginTop: 5,
  },
  statusContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 15,
    gap: 10,
  },
  statusLabel: {
    fontSize: 14,
    color: '#aaa',
  },
  statusBadge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 12,
  },
  statusBadgeLoading: {
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
  },
  statusBadgeConnected: {
    backgroundColor: 'rgba(0, 200, 0, 0.2)',
  },
  statusBadgeDisconnected: {
    backgroundColor: 'rgba(200, 0, 0, 0.2)',
  },
  statusText: {
    fontSize: 12,
    color: '#fff',
    fontWeight: 'bold',
  },
  retryLink: {
    fontSize: 12,
    color: '#ff6b00',
    textDecorationLine: 'underline',
  },
  content: {
    flex: 1,
    padding: 20,
    justifyContent: 'center',
  },
  mainButton: {
    backgroundColor: '#ff6b00',
    paddingVertical: 20,
    borderRadius: 15,
    alignItems: 'center',
    marginBottom: 30,
  },
  mainButtonDisabled: {
    backgroundColor: '#333',
    opacity: 0.5,
  },
  mainButtonText: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
  },
  infoBox: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 20,
    borderRadius: 10,
    marginBottom: 30,
  },
  infoText: {
    fontSize: 16,
    color: '#ddd',
    textAlign: 'center',
  },
  featuresContainer: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 20,
    borderRadius: 10,
  },
  featuresTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 15,
  },
  featureItem: {
    fontSize: 16,
    color: '#ddd',
    marginBottom: 8,
  },
  footer: {
    padding: 20,
    alignItems: 'center',
  },
  footerText: {
    fontSize: 12,
    color: '#666',
  },
});