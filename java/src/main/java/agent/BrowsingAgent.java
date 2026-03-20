package agent;

import dev.langchain4j.mcp.McpToolProvider;
import dev.langchain4j.mcp.client.DefaultMcpClient;
import dev.langchain4j.mcp.client.McpClient;
import dev.langchain4j.mcp.client.transport.stdio.StdioMcpTransport;
import dev.langchain4j.memory.chat.MessageWindowChatMemory;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.service.AiServices;
import dev.langchain4j.service.SystemMessage;

import java.util.List;

public class BrowsingAgent {

    interface Assistant {
        @SystemMessage("""
                You are a browser automation agent. Use browser tools to complete tasks step by step.
                After each action, assess the result and decide what to do next — don't stop until the task is done.
                When asked to find a link or element 'like X', match by text content or semantic meaning.
                If something unexpected happens (login wall, cookie banner, CAPTCHA), handle it before continuing.
                When writing Java tests, use Playwright for Java (com.microsoft.playwright) — no Selenium, no ChromeDriver.
                When writing tests: include EVERY step you performed — cookie banner dismissal, popups, overlays — nothing skipped.
                """)
        String chat(String message);
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 1) {
            System.out.println("Usage:");
            System.out.println("  test <journey> [--filename <file>] [--max-retries <n>]");
            System.exit(1);
        }

        // --- Parse args ---
        String command = args[0];
        String journey = null;
        String filename = "TestGenerated.java";
        int maxRetries = 3;

        for (int i = 1; i < args.length; i++) {
            switch (args[i]) {
                case "--filename" -> filename = args[++i];
                case "--max-retries" -> maxRetries = Integer.parseInt(args[++i]);
                default -> journey = args[i];
            }
        }

        if (!command.equals("test") || journey == null) {
            System.err.println("Error: expected: test <journey> [--filename <file>] [--max-retries <n>]");
            System.exit(1);
        }

        // --- Start MCP ---
        StdioMcpTransport transport = new StdioMcpTransport.Builder()
                .command(List.of("npx", "-y", "@playwright/mcp@latest"))
                .logEvents(false)
                .build();

        McpClient mcpClient = new DefaultMcpClient.Builder()
                .transport(transport)
                .build();

        // --- Build model ---
        String apiKey = System.getenv("OPENAI_API_KEY");
        if (apiKey == null || apiKey.isBlank()) {
            System.err.println("Error: OPENAI_API_KEY not set.");
            System.exit(1);
        }

        OpenAiChatModel model = OpenAiChatModel.builder()
                .apiKey(apiKey)
                .modelName("gpt-5.4")
                .build();

        // --- Build agent ---
        Assistant assistant = AiServices.builder(Assistant.class)
                .chatModel(model)
                .toolProvider(McpToolProvider.builder().mcpClients(List.of(mcpClient)).build())
                .tools(new TestTools())
                .chatMemory(MessageWindowChatMemory.withMaxMessages(50))
                .build();

        // --- Generate test ---
        System.out.println("\033[1mJourney:\033[0m " + journey + "\n");
        String prompt = String.format(
                "Follow this user journey step by step in the browser, noting every action you take " +
                "(including dismissing cookie banners, popups, or overlays): %s\n\n" +
                "Then write a Playwright Java test that reproduces every step exactly. " +
                "Save it as '%s' using createJavaFile, then run it with runJavaFile. " +
                "If it fails, read the error, fix the test, and run again. " +
                "Retry at most %d times before giving up.",
                journey, filename, maxRetries
        );

        String result = assistant.chat(prompt);
        System.out.println("\n" + result + "\n");

        mcpClient.close();
    }

    static void log(String msg) {
        System.out.println("\033[90m" + msg + "\033[0m");
        System.out.flush();
    }
}
