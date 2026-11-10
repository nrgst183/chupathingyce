/*
BOT_PEOPLE_WAYS.C

Written by tools/bot_people_ways.py from movement logs (debug.move_log): the
ways about the maps people took that the bots' navigation had none of, and
how they took them. Each: the map, where the feet left the ground and where
they came down, the way it was going (radians), how fast (units a second),
the tick after leaving the ground the crouch went down and came up (-1: no
crouch; 999: held to the landing), the person's time for it, the
navigation's time by its own ways then, and how many times it was taken.
*/

#include "bot_internal.h"

struct bot_people_way const bot_people_ways[] =
{
	{ "beavercreek", { 5.32f, 20.02f, -0.22f }, { 2.75f, 18.80f, -0.22f }, -2.698f, 2.25f, -1, -1, 1.30f, 2.4f, 1 },
	{ "beavercreek", { 8.55f, 18.21f, 1.03f }, { 6.02f, 18.60f, 1.11f }, 2.989f, 1.93f, 3, 9, 1.30f, 2.7f, 1 },
	{ "beavercreek", { 10.39f, 19.46f, -0.22f }, { 9.32f, 18.71f, 0.63f }, -2.530f, 2.25f, 8, 999, 0.60f, 1.1f, 1 },
	{ "beavercreek", { 10.92f, 14.72f, 0.45f }, { 11.71f, 16.17f, 0.95f }, 1.072f, 1.59f, 7, 18, 1.00f, 2.0f, 1 },
	{ "beavercreek", { 11.91f, 8.73f, -0.22f }, { 12.59f, 9.97f, 0.66f }, 1.069f, 2.25f, 8, 999, 0.70f, 1.7f, 1 },
	{ "beavercreek", { 17.38f, 13.04f, 0.42f }, { 16.48f, 11.41f, 1.00f }, -2.075f, 1.58f, -1, -1, 0.90f, 1.7f, 1 },
	{ "beavercreek", { 20.14f, 19.00f, -0.22f }, { 20.66f, 20.28f, 0.80f }, 1.185f, 2.25f, 6, 24, 0.90f, 17.6f, 1 },
	{ "beavercreek", { 21.43f, 6.45f, -0.22f }, { 21.53f, 7.45f, 1.05f }, 1.471f, 2.25f, 10, 999, 0.90f, 6.2f, 1 },
	{ "beavercreek", { 22.00f, 15.35f, 2.06f }, { 19.38f, 15.19f, -0.22f }, -3.081f, 2.25f, -1, -1, 1.20f, 2.2f, 1 },
	{ "beavercreek", { 22.81f, 11.41f, 2.06f }, { 22.88f, 12.71f, 3.01f }, 1.517f, 2.25f, 6, 24, 0.90f, 3.0f, 1 },
	{ "beavercreek", { 24.14f, 11.68f, 2.06f }, { 23.34f, 12.84f, 3.01f }, 2.175f, 2.25f, 9, 25, 0.90f, 2.7f, 1 },
	{ "beavercreek", { 25.59f, 18.03f, 0.66f }, { 25.90f, 17.23f, 1.40f }, -1.201f, 0.95f, 5, 18, 0.80f, 2.3f, 1 },
	{ "beavercreek", { 27.38f, 20.39f, -0.22f }, { 28.44f, 19.43f, 0.74f }, -0.736f, 2.25f, 5, 23, 0.90f, 5.1f, 1 },
	{ "carousel", { -8.37f, -6.21f, -0.86f }, { -10.21f, -3.84f, -0.86f }, 2.231f, 2.25f, -1, -1, 1.30f, 2.5f, 1 },
	{ "carousel", { 4.76f, 0.48f, -2.56f }, { 4.52f, 2.90f, -2.56f }, 1.670f, 2.25f, -1, -1, 1.10f, 1.8f, 1 },
	{ "chillout", { -6.43f, 7.60f, -0.00f }, { -7.13f, 5.69f, 0.50f }, -1.922f, 2.25f, 7, 12, 1.00f, 1.9f, 1 },
	{ "chillout", { -5.98f, 7.34f, -0.00f }, { -6.96f, 5.32f, 0.50f }, -2.022f, 2.25f, -1, -1, 1.00f, 1.8f, 1 },
	{ "chillout", { -3.45f, 10.89f, 0.28f }, { -4.91f, 8.69f, 0.50f }, -2.157f, 2.06f, -1, -1, 1.20f, 1.9f, 1 },
	{ "chillout", { -0.12f, -0.05f, 2.78f }, { 2.68f, -0.64f, 2.38f }, -0.208f, 2.25f, -1, -1, 1.50f, 2.7f, 1 },
	{ "chillout", { -0.01f, -0.10f, 2.78f }, { 3.15f, -0.45f, 2.38f }, -0.110f, 2.25f, 16, 24, 1.50f, 3.4f, 1 },
	{ "chillout", { 0.33f, -0.31f, 2.78f }, { 2.32f, -0.31f, 0.23f }, 0.000f, 1.92f, -1, -1, 1.20f, 2.0f, 1 },
	{ "chillout", { 1.60f, 4.50f, 3.11f }, { 3.81f, 3.49f, 0.75f }, -0.429f, 2.25f, -1, -1, 1.20f, 1.7f, 1 },
	{ "chillout", { 1.89f, 0.27f, 0.23f }, { 1.89f, 2.36f, 0.75f }, 1.571f, 2.25f, 12, 23, 1.00f, 2.1f, 1 },
	{ "chillout", { 2.69f, -0.56f, 2.38f }, { 1.08f, 2.98f, 0.75f }, 1.998f, 1.60f, -1, -1, 1.90f, 3.2f, 1 },
	{ "chillout", { 2.73f, -0.49f, 2.38f }, { 0.42f, -0.26f, 2.76f }, 3.042f, 2.25f, 15, 24, 1.10f, 2.6f, 3 },
	{ "chillout", { 7.13f, -1.23f, 2.38f }, { 8.85f, -1.74f, 3.19f }, -0.288f, 2.25f, 8, 999, 0.90f, 1.8f, 1 },
	{ "chillout", { 8.70f, -1.25f, 3.40f }, { 6.67f, -0.56f, 2.38f }, 2.814f, 2.23f, -1, -1, 1.00f, 2.0f, 1 },
	{ "damnation", { -2.00f, 1.03f, -0.20f }, { -2.06f, -1.52f, -0.20f }, -1.594f, 2.25f, -1, -1, 1.30f, 2.7f, 1 },
	{ "damnation", { -1.03f, 14.48f, 1.64f }, { -4.70f, 14.75f, 0.81f }, 3.068f, 2.15f, -1, -1, 1.60f, 2.3f, 1 },
	{ "damnation", { 0.67f, -4.42f, 7.85f }, { -0.44f, -2.20f, 8.20f }, 2.034f, 2.15f, -1, -1, 1.10f, 2.8f, 1 },
	{ "prisoner", { -7.22f, -3.17f, 1.39f }, { -7.67f, -6.02f, 1.39f }, -1.727f, 2.25f, 12, 17, 1.30f, 2.2f, 1 },
	{ "prisoner", { -7.04f, 2.72f, 3.19f }, { -4.14f, 2.02f, 3.19f }, -0.237f, 2.25f, -1, -1, 1.30f, 2.1f, 1 },
	{ "prisoner", { -4.21f, -4.25f, 1.39f }, { -6.73f, -3.17f, 1.39f }, 2.737f, 2.25f, 14, 25, 1.30f, 5.0f, 1 },
	{ "prisoner", { 1.66f, 1.87f, 3.19f }, { -1.28f, 1.67f, 3.19f }, -3.074f, 2.25f, 20, 24, 1.30f, 3.4f, 1 },
	{ "putput", { -5.79f, -2.78f, 2.20f }, { -3.94f, -2.73f, 0.90f }, 0.027f, 2.25f, -1, -1, 0.90f, 1.8f, 1 },
	{ "putput", { 32.50f, -26.56f, 1.00f }, { 33.61f, -26.52f, 0.45f }, 0.036f, 2.13f, -1, -1, 0.50f, 1.3f, 1 },
	{ "putput", { 33.84f, -26.74f, 0.29f }, { 32.67f, -28.02f, 1.00f }, -2.311f, 2.20f, 6, 21, 0.90f, 1.5f, 1 },
	{ NULL }
};

long const bot_people_way_count = 37;
