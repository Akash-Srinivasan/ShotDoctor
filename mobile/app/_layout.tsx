import { Stack } from 'expo-router';

export default function RootLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: {
          backgroundColor: '#000',
        },
        headerTintColor: '#fff',
        headerTitleStyle: {
          fontWeight: 'bold',
        },
      }}
    >
      <Stack.Screen
        name="index"
        options={{
          title: 'FormCheck',
        }}
      />
      <Stack.Screen
        name="record"
        options={{
          title: 'Record Shot',
          headerShown: false,
        }}
      />
    </Stack>
  );
}