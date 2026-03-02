import React, { Component, type ReactNode } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('ErrorBoundary caught:', error, info.componentStack);
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  handleGoHome = () => {
    this.setState({ hasError: false, error: null });
    // Dynamic import to avoid circular deps at module load time
    const { router } = require('expo-router');
    router.replace('/(tabs)');
  };

  render() {
    if (this.state.hasError) {
      return (
        <View style={styles.container}>
          <Ionicons name="warning-outline" size={48} color="#FF4D00" />
          <Text style={styles.title}>Something went wrong</Text>
          <Text style={styles.subtitle}>
            This screen ran into an error. You can try again or go back home.
          </Text>

          {this.state.error && (
            <Text style={styles.errorDetail} numberOfLines={4}>
              {this.state.error.message}
            </Text>
          )}

          <TouchableOpacity style={styles.retryButton} onPress={this.handleRetry}>
            <Ionicons name="refresh" size={18} color="#FFF" />
            <Text style={styles.retryText}>Try Again</Text>
          </TouchableOpacity>

          <TouchableOpacity style={styles.homeButton} onPress={this.handleGoHome}>
            <Text style={styles.homeText}>Go Home</Text>
          </TouchableOpacity>
        </View>
      );
    }

    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 32,
  },
  title: {
    fontSize: 20,
    fontWeight: '700',
    color: '#FFF',
    marginTop: 16,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: '#888',
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 16,
  },
  errorDetail: {
    fontSize: 12,
    color: '#555',
    textAlign: 'center',
    marginBottom: 24,
    fontFamily: 'Courier',
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FF4D00',
    borderRadius: 100,
    paddingVertical: 14,
    paddingHorizontal: 28,
    gap: 8,
    marginBottom: 12,
  },
  retryText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#FFF',
  },
  homeButton: {
    borderRadius: 100,
    paddingVertical: 14,
    paddingHorizontal: 28,
    borderWidth: 1,
    borderColor: '#2A2A2A',
  },
  homeText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#FFF',
  },
});
