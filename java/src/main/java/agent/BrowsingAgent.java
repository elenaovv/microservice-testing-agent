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
                Call logAction after every meaningful browser interaction — record what you did and why.
                Use startTimer / stopTimer around slow steps (page load, search results, navigation).
                When writing Playwright Java tests: never manage the browser in main() — use a proper test runner pattern.
                If a cookie consent banner appeared, dismissing it must be the FIRST step after navigation.
                Use the logged actions and measured timings to write the test — include every step, nothing skipped.
                Set per-step timeouts to 2-3x the observed duration from your timers.
                If a test fails and a screenshot path is returned, describe what you see in it to understand the failure.
                """)
        String chat(String message);
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2 || !args[0].equals("test")) {
            System.out.println("Usage: test <journey> [--filename <file>] [--max-retries <n>]");
            System.exit(1);
        }

        String journey = null;
        String filename = "TestGenerated.java";
        int maxRetries = 3;

        for (int i = 1; i < args.length; i++) {
            switch (args[i]) {
                case "--filename"    -> filename = args[++i];
                case "--max-retries" -> maxRetries = Integer.parseInt(args[++i]);
                default              -> journey = args[i];
            }
        }

        if (journey == null) {
            System.err.println("Error: journey description required.");
            System.exit(1);
        }

        // --- Start MCP ---
        McpClient mcpClient = new DefaultMcpClient.Builder()
                .transport(new StdioMcpTransport.Builder()
                        .command(List.of("npx", "-y", "@playwright/mcp@latest"))
                        .logEvents(false)
                        .build())
                .build();

        // --- Build model ---
        String apiKey = System.getenv("OPENAI_API_KEY");
        if (apiKey == null || apiKey.isBlank()) {
            System.err.println("Error: OPENAI_API_KEY not set.");
            System.exit(1);
        }

        TestTools tools = new TestTools();

        Assistant assistant = AiServices.builder(Assistant.class)
                .chatModel(OpenAiChatModel.builder().apiKey(apiKey).modelName("gpt-5.4").build())
                .toolProvider(McpToolProvider.builder().mcpClients(List.of(mcpClient)).build())
                .tools(tools)
                .chatMemory(MessageWindowChatMemory.withMaxMessages(50))
                .build();

        // --- Phase 1: navigate and log actions ---
        System.out.println("\033[1mJourney:\033[0m " + journey + "\n");
        assistant.chat(
                "Follow this user journey step by step in the browser. " +
                "Call logAction after every interaction and use startTimer/stopTimer around slow steps. " +
                "Journey: " + journey
        );

        // --- Phase 2: write and validate test ---
        String actionSummary = tools.actionSummary();
        String result = assistant.chat(
                "Using your logged actions below, write a Playwright Java test that reproduces every step exactly.\n\n" +
                "Logged actions:\n" + actionSummary + "\n\n" +
                "Save it as '" + filename + "' using createJavaFile, then run it with runJavaFile. " +
                "If it fails, read the error and screenshot description, fix and retry at most " + maxRetries + " times."
        );

        System.out.println("\n" + result + "\n");
        mcpClient.close();
    }

    static void log(String msg) {
        System.out.println("\033[90m" + msg + "\033[0m");
        System.out.flush();
    }
}
