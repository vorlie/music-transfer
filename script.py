from ytmusicapi import YTMusic, OAuthCredentials

yt = YTMusic("oauth.json", oauth_credentials=OAuthCredentials(client_id="", client_secret=""))

print("Creating playlist...")
playlistId = yt.create_playlist("test", "test description")
search_results = yt.search("Oasis Wonderwall")
yt.add_playlist_items(playlistId, [search_results[0]["videoId"]])
print("Successfully created playlist")